"""Gestão do evento pelo organizador: convidados, baixa manual, painel, cancelamento, prazo."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.organizador import _evento_do_organizador
from app.config import get_settings
from app.db import get_session
from app.domain.estados import TransicaoInvalida
from app.domain.mensagens import TipoMensagem
from app.domain.prazo import calcular_prazo
from app.security import OrganizadorAtual
from app.services import storage
from app.services.cobranca import SQL_VALOR_PAGO
from app.services.mensageria import enfileirar_mensagem
from app.services.pagamentos import confirmar_pagamento_manual

log = logging.getLogger(__name__)
router = APIRouter(prefix="/eventos/{evento_id}", tags=["gestão do evento"])
Sessao = Annotated[AsyncSession, Depends(get_session)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ConvidadoLinha(BaseModel):
    id: UUID
    nome: str
    telefone_e164: str
    status: str
    qtd_acompanhantes: int
    valor_devido: Decimal  # total
    valor_pago: Decimal
    valor_a_pagar: Decimal  # o que falta (ex.: acompanhante a mais depois de pagar)
    opt_out: bool
    link: str
    convidado_em: datetime
    confirmado_em: datetime | None
    ultima_mensagem_status: str | None
    comprovante_recebido_em: datetime | None


class BaixaManualIn(BaseModel):
    valor: Decimal = Field(gt=0)
    observacao: str | None = Field(default=None, max_length=500)


class ColaboracaoPainel(BaseModel):
    descricao: str
    tipo: str
    meta: Decimal | None
    arrecadado: Decimal
    projetado: Decimal


class PainelOut(BaseModel):
    por_status: dict[str, int]
    pessoas_confirmadas: int
    prazo_vencido_pendentes: int
    arrecadado_total: Decimal
    colaboracoes: list[ColaboracaoPainel]
    mensagens_com_falha: int
    comprovantes_pendentes: int


def _link(token: str) -> str:
    return f"{get_settings().url_publica_front.rstrip('/')}/c/{token}"


async def _convidado_do_evento(sessao: AsyncSession, evento_id: UUID, convidado_id: UUID):
    res = await sessao.execute(
        text("select * from convidado where id = :cid and evento_id = :ev for update"),
        {"cid": convidado_id, "ev": evento_id},
    )
    c = res.mappings().first()
    if c is None:
        raise HTTPException(404, "Convidado não encontrado")
    return c


# ---------------------------------------------------------------------------
# Convidados
# ---------------------------------------------------------------------------
@router.get("/convidados", response_model=list[ConvidadoLinha])
async def listar_convidados(
    evento_id: UUID, org: OrganizadorAtual, sessao: Sessao
) -> list[ConvidadoLinha]:
    await _evento_do_organizador(sessao, evento_id, org.id)
    res = await sessao.execute(
        text(f"""
            select c.id, c.nome, c.telefone_e164, c.status::text as status, c.qtd_acompanhantes,
                   c.valor_devido, {SQL_VALOR_PAGO} as valor_pago,
                   greatest(c.valor_devido - {SQL_VALOR_PAGO}, 0) as valor_a_pagar,
                   c.opt_out, c.token, c.convidado_em, c.confirmado_em,
                   c.comprovante_recebido_em,
                   (select m.status::text from mensagem m where m.convidado_id = c.id
                     order by m.criado_em desc limit 1) as ultima_mensagem_status
              from convidado c
             where c.evento_id = :id
             order by c.nome
        """),
        {"id": evento_id},
    )
    return [
        ConvidadoLinha(**{k: v for k, v in r.items() if k != "token"}, link=_link(r["token"]))
        for r in res.mappings()
    ]


class MensagemHistorico(BaseModel):
    tipo: str
    status: str  # PENDENTE | ENVIADA | ENTREGUE | LIDA | FALHA
    conteudo: str
    criado_em: datetime
    enviada_em: datetime | None
    erro: str | None


class PagamentoHistorico(BaseModel):
    tipo: str  # CONTRIBUICAO | PRESENTE
    presente: str | None
    valor: Decimal
    status: str
    origem: str  # MERCADO_PAGO | MANUAL
    observacao: str | None
    criado_em: datetime
    pago_em: datetime | None


class HistoricoOut(BaseModel):
    mensagens: list[MensagemHistorico]
    pagamentos: list[PagamentoHistorico]


@router.get("/convidados/{convidado_id}/historico", response_model=HistoricoOut)
async def historico_convidado(
    evento_id: UUID, convidado_id: UUID, org: OrganizadorAtual, sessao: Sessao
) -> HistoricoOut:
    """RF-DSH-04: tudo o que aconteceu com um convidado, do mais recente para o mais antigo."""
    await _evento_do_organizador(sessao, evento_id, org.id)
    existe = await sessao.execute(
        text("select 1 from convidado where id = :c and evento_id = :ev"),
        {"c": convidado_id, "ev": evento_id},
    )
    if existe.first() is None:
        raise HTTPException(404, "Convidado não encontrado")
    mensagens = await sessao.execute(
        text("""
            select tipo::text as tipo, status::text as status, conteudo, criado_em, enviada_em,
                   case when status = 'FALHA' then erro end as erro
              from mensagem where convidado_id = :c
             order by criado_em desc
        """),
        {"c": convidado_id},
    )
    pagamentos = await sessao.execute(
        text("""
            select pg.tipo::text as tipo, p.nome as presente, pg.valor_liquido as valor,
                   pg.status::text as status, pg.origem::text as origem, pg.observacao,
                   pg.criado_em, pg.pago_em
              from pagamento pg left join presente p on p.id = pg.presente_id
             where pg.convidado_id = :c
             order by pg.criado_em desc
        """),
        {"c": convidado_id},
    )
    return HistoricoOut(
        mensagens=[MensagemHistorico(**m) for m in mensagens.mappings()],
        pagamentos=[PagamentoHistorico(**p) for p in pagamentos.mappings()],
    )


@router.post("/convidados/{convidado_id}/reenviar")
async def reenviar_convite(
    evento_id: UUID, convidado_id: UUID, org: OrganizadorAtual, sessao: Sessao
) -> dict:
    ev = await _evento_do_organizador(sessao, evento_id, org.id)
    if ev["status"] != "ATIVO":
        raise HTTPException(409, "Ative o evento para enviar convites")
    await _convidado_do_evento(sessao, evento_id, convidado_id)
    await enfileirar_mensagem(sessao, convidado_id, TipoMensagem.CONVITE)
    await sessao.commit()
    return {"ok": True}


@router.delete("/convidados/{convidado_id}", status_code=204)
async def remover_convidado(
    evento_id: UUID, convidado_id: UUID, org: OrganizadorAtual, sessao: Sessao
) -> None:
    await _evento_do_organizador(sessao, evento_id, org.id)
    await _convidado_do_evento(sessao, evento_id, convidado_id)
    pago = await sessao.execute(
        text("select 1 from pagamento where convidado_id = :id and status = 'APROVADO'"),
        {"id": convidado_id},
    )
    if pago.first():
        # Mantém o histórico financeiro: quem já pagou não pode ser apagado
        raise HTTPException(409, "Convidado já pagou — não é possível remover")
    await sessao.execute(text("delete from convidado where id = :id"), {"id": convidado_id})
    await sessao.commit()


@router.post("/convidados/{convidado_id}/baixa-manual")
async def baixa_manual(
    evento_id: UUID,
    convidado_id: UUID,
    dados: BaixaManualIn,
    org: OrganizadorAtual,
    sessao: Sessao,
) -> dict:
    """RF-PGT-08: pagamento por fora (dinheiro, PIX direto) confirma a presença."""
    ev = await _evento_do_organizador(sessao, evento_id, org.id)
    if not ev["tem_contribuicao"]:
        raise HTTPException(409, "Evento sem contribuição")
    c = await _convidado_do_evento(sessao, evento_id, convidado_id)
    try:
        novo = await confirmar_pagamento_manual(
            sessao,
            convidado_id=convidado_id,
            valor=dados.valor,
            observacao=dados.observacao,
            comprovante_path=c["comprovante_path"],
        )
    except TransicaoInvalida as e:
        raise HTTPException(409, str(e)) from e
    await sessao.commit()
    return {"status": novo.value}


# ---------------------------------------------------------------------------
# Comprovantes recebidos pelo WhatsApp (modo PIX manual)
# ---------------------------------------------------------------------------
class ComprovanteLinha(BaseModel):
    convidado_id: UUID
    nome: str
    telefone_e164: str
    valor_devido: Decimal
    recebido_em: datetime
    imagem_url: str | None  # URL assinada (1 h); None se a mídia não foi guardada
    analise: dict | None  # app/domain/comprovante.py → Analise.para_json()


@router.get("/comprovantes", response_model=list[ComprovanteLinha])
async def listar_comprovantes(
    evento_id: UUID, org: OrganizadorAtual, sessao: Sessao
) -> list[ComprovanteLinha]:
    """Fila "para conferir": convidados que mandaram comprovante e ainda não foram confirmados."""
    await _evento_do_organizador(sessao, evento_id, org.id)
    res = await sessao.execute(
        text(f"""
            select c.id, c.nome, c.telefone_e164, c.comprovante_recebido_em, c.comprovante_path,
                   c.comprovante_analise,
                   greatest(c.valor_devido - {SQL_VALOR_PAGO}, 0) as valor_devido
              from convidado c
             where c.evento_id = :id and c.comprovante_recebido_em is not null
               and c.status <> 'CONFIRMADO'
             order by c.comprovante_recebido_em
        """),
        {"id": evento_id},
    )
    saida = []
    for r in res.mappings():
        url = None
        if r["comprovante_path"]:
            try:
                url = await storage.url_assinada(storage.BUCKET_COMPROVANTES, r["comprovante_path"])
            except storage.ErroStorage as e:
                log.warning("URL do comprovante falhou: %s", e)
        saida.append(
            ComprovanteLinha(
                convidado_id=r["id"],
                nome=r["nome"],
                telefone_e164=r["telefone_e164"],
                valor_devido=r["valor_devido"],
                recebido_em=r["comprovante_recebido_em"],
                imagem_url=url,
                analise=r["comprovante_analise"],
            )
        )
    return saida


@router.post("/convidados/{convidado_id}/comprovante/recusar")
async def recusar_comprovante(
    evento_id: UUID, convidado_id: UUID, org: OrganizadorAtual, sessao: Sessao
) -> dict:
    """Tira da fila sem confirmar (ex.: imagem errada). O convidado continua pendente."""
    await _evento_do_organizador(sessao, evento_id, org.id)
    await _convidado_do_evento(sessao, evento_id, convidado_id)
    await sessao.execute(
        text("""
            update convidado
               set comprovante_recebido_em = null, comprovante_path = null,
                   comprovante_analise = null, comprovante_e2e = null
             where id = :id
        """),
        {"id": convidado_id},
    )
    await sessao.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Evento
# ---------------------------------------------------------------------------
@router.get("/painel", response_model=PainelOut)
async def painel(evento_id: UUID, org: OrganizadorAtual, sessao: Sessao) -> PainelOut:
    await _evento_do_organizador(sessao, evento_id, org.id)
    p = {"id": evento_id}

    res = await sessao.execute(
        text(
            "select status::text as status, count(*) as n from convidado "
            "where evento_id = :id group by status"
        ),
        p,
    )
    por_status = {r["status"]: r["n"] for r in res.mappings()}

    res = await sessao.execute(
        text("""
            select
              coalesce(sum(1 + c.qtd_acompanhantes)
                       filter (where c.status = 'CONFIRMADO'), 0) as pessoas,
              count(c.id) filter (where c.status in ('CONVIDADO', 'AGUARDANDO_PAGAMENTO')
                                    and e.prazo_pagamento < current_date) as vencidos,
              (select coalesce(sum(pg.valor_liquido), 0) from pagamento pg
                 join convidado c2 on c2.id = pg.convidado_id
                where c2.evento_id = :id and pg.status = 'APROVADO'
                  and pg.tipo = 'CONTRIBUICAO') as arrecadado,
              (select count(*) from mensagem m join convidado c3 on c3.id = m.convidado_id
                where c3.evento_id = :id and m.status = 'FALHA') as falhas,
              (select count(*) from convidado c4
                where c4.evento_id = :id and c4.comprovante_recebido_em is not null
                  and c4.status <> 'CONFIRMADO') as comprovantes
            from evento e left join convidado c on c.evento_id = e.id
           where e.id = :id
           group by e.id
        """),
        p,
    )
    resumo = res.mappings().one()

    res = await sessao.execute(
        text("""
            select descricao, tipo::text as tipo, meta, arrecadado, projetado
              from vw_arrecadacao_colaboracao where evento_id = :id
        """),
        p,
    )
    return PainelOut(
        por_status=por_status,
        pessoas_confirmadas=resumo["pessoas"],
        prazo_vencido_pendentes=resumo["vencidos"],
        arrecadado_total=resumo["arrecadado"],
        colaboracoes=[ColaboracaoPainel(**c) for c in res.mappings()],
        mensagens_com_falha=resumo["falhas"],
        comprovantes_pendentes=resumo["comprovantes"],
    )


@router.post("/cancelar")
async def cancelar_evento(evento_id: UUID, org: OrganizadorAtual, sessao: Sessao) -> dict:
    """RF-EVT-07: cancela e avisa quem não recusou."""
    ev = await _evento_do_organizador(sessao, evento_id, org.id)
    if ev["status"] in ("CANCELADO", "ENCERRADO"):
        raise HTTPException(409, f"Evento já está {ev['status']}")

    avisar: list[UUID] = []
    if ev["status"] == "ATIVO":
        res = await sessao.execute(
            text("select id from convidado where evento_id = :id and status <> 'RECUSOU'"),
            {"id": evento_id},
        )
        avisar = list(res.scalars().all())
        for cid in avisar:
            await enfileirar_mensagem(sessao, cid, TipoMensagem.CANCELAMENTO)

    await sessao.execute(
        text("""
            update pagamento set status = 'CANCELADO'
             where status = 'PENDENTE'
               and convidado_id in (select id from convidado where evento_id = :id)
        """),
        {"id": evento_id},
    )
    await sessao.execute(
        text("update evento set status = 'CANCELADO' where id = :id"), {"id": evento_id}
    )
    await sessao.commit()
    return {"status": "CANCELADO", "avisados": len(avisar)}


@router.post("/prazo/recalcular")
async def recalcular_prazo(evento_id: UUID, org: OrganizadorAtual, sessao: Sessao) -> dict:
    """Chamado após editar a data de um evento ATIVO (quando o prazo não é manual)."""
    ev = await _evento_do_organizador(sessao, evento_id, org.id)
    if ev["prazo_manual"] or not ev["tem_contribuicao"] or ev["status"] != "ATIVO":
        return {"prazo_pagamento": ev["prazo_pagamento"], "alterado": False}
    fuso = ZoneInfo(get_settings().fuso)
    prazo = calcular_prazo(ev["data_hora"].astimezone(fuso).date(), datetime.now(fuso).date())
    await sessao.execute(
        text("update evento set prazo_pagamento = :p where id = :id"),
        {"p": prazo, "id": evento_id},
    )
    await sessao.commit()
    return {"prazo_pagamento": prazo, "alterado": prazo != ev["prazo_pagamento"]}
