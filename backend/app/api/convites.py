"""Endpoints públicos do convidado (acesso pelo token do link, sem login).

GET  /convites/{token}            → dados do evento + situação do convidado
POST /convites/{token}/resposta   → "Vou" / "Não vou" + acompanhantes
POST /convites/{token}/pagamento  → gera (ou reaproveita) a cobrança PIX
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.domain.estados import AcaoConvidado, StatusConvidado, TransicaoInvalida, transicionar
from app.domain.pix import gerar_copia_cola, txid_do_convidado
from app.domain.prazo import prazo_vencido
from app.integrations.mercadopago import ErroMercadoPago, MercadoPagoClient
from app.security import descriptografar
from app.services.cobranca import link_whatsapp_comprovante, modo_pagamento

router = APIRouter(prefix="/convites", tags=["convidado"])
Sessao = Annotated[AsyncSession, Depends(get_session)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ItemSimples(BaseModel):
    nome: str
    descricao: str | None = None


class ColaboracaoOut(BaseModel):
    descricao: str
    valor_por_pessoa: Decimal


class ConviteOut(BaseModel):
    convidado_nome: str
    status: StatusConvidado
    qtd_acompanhantes: int
    max_acompanhantes: int | None
    evento_nome: str
    evento_descricao: str | None
    data_hora: datetime
    local_nome: str | None
    endereco: str | None
    mapa_url: str | None
    capa_url: str | None
    convite_imagem_url: str | None
    tem_contribuicao: bool
    colaboracoes: list[ColaboracaoOut]
    atracoes: list[ItemSimples]
    cardapio: list[ItemSimples]
    valor_devido: Decimal
    valor_cobrado: Decimal | None
    modo_pagamento: str  # MERCADO_PAGO | PIX_MANUAL | NENHUM
    comprovante_recebido: bool
    prazo_pagamento: date | None
    prazo_vencido: bool


class RespostaIn(BaseModel):
    vou: bool
    qtd_acompanhantes: int = Field(default=0, ge=0, le=20)


class PagamentoOut(BaseModel):
    modo: str  # MERCADO_PAGO | PIX_MANUAL
    valor: Decimal
    pix_copia_cola: str | None
    pix_qr_base64: str | None = None
    status: str
    # Mercado Pago
    pagamento_id: UUID | None = None
    expira_em: datetime | None = None
    # PIX manual
    pix_chave: str | None = None
    pix_nome: str | None = None
    whatsapp_url: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_SQL_CONVIDADO = text("""
    select c.id, c.nome, c.status, c.qtd_acompanhantes, c.valor_por_pessoa, c.valor_devido,
           c.comprovante_recebido_em,
           e.id as evento_id, e.organizador_id, e.nome as evento_nome, e.descricao, e.data_hora,
           e.local_nome, e.endereco, e.mapa_url, e.capa_url, e.convite_imagem_url,
           e.tem_contribuicao,
           e.max_acompanhantes, e.prazo_pagamento, e.taxa_mp, e.status as evento_status
      from convidado c
      join evento e on e.id = c.evento_id
     where c.token = :token
""")


async def _carregar(sessao: AsyncSession, token: str, *, para_update: bool = False):
    sql = _SQL_CONVIDADO
    if para_update:
        sql = text(str(_SQL_CONVIDADO) + " for update of c")
    row = (await sessao.execute(sql, {"token": token})).mappings().first()
    if row is None or row["evento_status"] in ("RASCUNHO",):
        raise HTTPException(404, "Convite não encontrado")
    return row


def _hoje() -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(get_settings().fuso)).date()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/{token}", response_model=ConviteOut)
async def ver_convite(token: str, sessao: Sessao) -> ConviteOut:
    c = await _carregar(sessao, token)
    params = {"evento_id": c["evento_id"], "convidado_id": c["id"]}

    colabs = (
        await sessao.execute(
            text("""
                select col.descricao, cc.valor_por_pessoa
                  from convidado_colaboracao cc
                  join colaboracao col on col.id = cc.colaboracao_id
                 where cc.convidado_id = :convidado_id
                 order by col.ordem
            """),
            params,
        )
    ).mappings()
    atracoes = (
        await sessao.execute(
            text("select nome, descricao from atracao where evento_id = :evento_id order by ordem"),
            params,
        )
    ).mappings()
    cardapio = (
        await sessao.execute(
            text(
                "select nome, descricao from item_cardapio where evento_id = :evento_id "
                "order by ordem"
            ),
            params,
        )
    ).mappings()

    devido = Decimal(c["valor_devido"])
    prazo = c["prazo_pagamento"]
    modo = await modo_pagamento(sessao, c["organizador_id"])
    return ConviteOut(
        convidado_nome=c["nome"],
        status=c["status"],
        qtd_acompanhantes=c["qtd_acompanhantes"],
        max_acompanhantes=c["max_acompanhantes"],
        evento_nome=c["evento_nome"],
        evento_descricao=c["descricao"],
        data_hora=c["data_hora"],
        local_nome=c["local_nome"],
        endereco=c["endereco"],
        mapa_url=c["mapa_url"],
        capa_url=c["capa_url"],
        convite_imagem_url=c["convite_imagem_url"],
        tem_contribuicao=c["tem_contribuicao"],
        colaboracoes=[ColaboracaoOut(**r) for r in colabs],
        atracoes=[ItemSimples(**r) for r in atracoes],
        cardapio=[ItemSimples(**r) for r in cardapio],
        valor_devido=devido,
        valor_cobrado=modo.valor_cobrado(devido, Decimal(c["taxa_mp"])) if devido > 0 else None,
        modo_pagamento=modo.modo,
        comprovante_recebido=c["comprovante_recebido_em"] is not None,
        prazo_pagamento=prazo,
        prazo_vencido=bool(prazo and prazo_vencido(prazo, _hoje())),
    )


@router.post("/{token}/resposta", response_model=ConviteOut)
async def responder(token: str, dados: RespostaIn, sessao: Sessao) -> ConviteOut:
    c = await _carregar(sessao, token, para_update=True)
    if c["evento_status"] != "ATIVO":
        raise HTTPException(409, "Este evento não está aceitando respostas")

    max_acomp = c["max_acompanhantes"]
    if max_acomp is not None and dados.qtd_acompanhantes > max_acomp:
        raise HTTPException(422, f"Máximo de {max_acomp} acompanhante(s)")

    status_atual = StatusConvidado(c["status"])
    if status_atual is StatusConvidado.CONFIRMADO and c["tem_contribuicao"]:
        # RF-PAG-04: após pagar, mudar acompanhantes exige cobrar a diferença (TODO fase 2)
        if dados.qtd_acompanhantes != c["qtd_acompanhantes"] or not dados.vou:
            raise HTTPException(409, "Presença já paga — fale com o organizador para alterar")

    acao = AcaoConvidado.ACEITAR if dados.vou else AcaoConvidado.RECUSAR
    try:
        novo = transicionar(status_atual, acao, tem_contribuicao=c["tem_contribuicao"])
    except TransicaoInvalida as e:
        raise HTTPException(409, str(e)) from e

    await sessao.execute(
        text("""
            update convidado
               set status = cast(:status as status_convidado), qtd_acompanhantes = :acomp,
                   respondeu_em = now(),
                   confirmado_em = case when cast(:status as status_convidado) = 'CONFIRMADO'
                                        then now() else confirmado_em end
             where id = :id
        """),
        {"status": novo.value, "acomp": dados.qtd_acompanhantes, "id": c["id"]},
    )
    # Mudou o valor → cancela cobrança pendente antiga (será gerada de novo ao clicar "Pagar")
    await sessao.execute(
        text("""
            update pagamento set status = 'CANCELADO'
             where convidado_id = :id and tipo = 'CONTRIBUICAO' and status = 'PENDENTE'
        """),
        {"id": c["id"]},
    )
    await sessao.commit()
    return await ver_convite(token, sessao)


@router.post("/{token}/pagamento", response_model=PagamentoOut)
async def gerar_pagamento(token: str, sessao: Sessao) -> PagamentoOut:
    c = await _carregar(sessao, token, para_update=True)
    if c["evento_status"] != "ATIVO" or not c["tem_contribuicao"]:
        raise HTTPException(409, "Este evento não tem pagamento disponível")
    if c["status"] != StatusConvidado.AGUARDANDO_PAGAMENTO.value:
        raise HTTPException(409, "Confirme sua presença antes de pagar")

    modo = await modo_pagamento(sessao, c["organizador_id"])
    if modo.modo == "PIX_MANUAL":
        devido = Decimal(c["valor_devido"])
        copia_cola = gerar_copia_cola(
            chave=modo.pix_chave or "",
            nome=modo.pix_nome or "Organizador",
            cidade=modo.pix_cidade or "Brasil",
            valor=devido,
            txid=txid_do_convidado(str(c["id"])),
        )
        return PagamentoOut(
            modo="PIX_MANUAL",
            valor=devido,
            pix_copia_cola=copia_cola,
            status="AGUARDANDO_COMPROVANTE",
            pix_chave=modo.pix_chave,
            pix_nome=modo.pix_nome,
            whatsapp_url=link_whatsapp_comprovante(
                modo.whatsapp_numero or "", c["nome"], c["evento_nome"], devido
            ),
        )
    if modo.modo != "MERCADO_PAGO":
        raise HTTPException(503, "Pagamento indisponível no momento — avise o organizador")

    # Reaproveita cobrança pendente ainda válida
    existente = (
        (
            await sessao.execute(
                text("""
                select id, valor_cobrado, pix_copia_cola, pix_qr_base64, expira_em, status
                  from pagamento
                 where convidado_id = :id and tipo = 'CONTRIBUICAO' and status = 'PENDENTE'
                   and expira_em > now() + interval '5 minutes'
            """),
                {"id": c["id"]},
            )
        )
        .mappings()
        .first()
    )
    if existente:
        return PagamentoOut(
            modo="MERCADO_PAGO",
            pagamento_id=existente["id"],
            valor=existente["valor_cobrado"],
            pix_copia_cola=existente["pix_copia_cola"],
            pix_qr_base64=existente["pix_qr_base64"],
            expira_em=existente["expira_em"],
            status=existente["status"],
        )

    integ = (
        await sessao.execute(
            text(
                "select access_token_enc from integracao_mp "
                "where organizador_id = :org and status = 'ATIVA'"
            ),
            {"org": c["organizador_id"]},
        )
    ).first()
    if integ is None:
        raise HTTPException(503, "Pagamento indisponível no momento — avise o organizador")

    # Cancela pendentes vencidas/antigas (índice único permite só uma pendente)
    await sessao.execute(
        text("""
            update pagamento set status = 'EXPIRADO'
             where convidado_id = :id and tipo = 'CONTRIBUICAO' and status = 'PENDENTE'
        """),
        {"id": c["id"]},
    )

    liquido = Decimal(c["valor_devido"])
    cobrado = modo.valor_cobrado(liquido, Decimal(c["taxa_mp"]))
    pagamento_id = uuid4()
    expira_em = datetime.now(UTC) + timedelta(days=1)

    mp = MercadoPagoClient(
        access_token=descriptografar(integ[0]), base_url=get_settings().mp_api_base
    )
    try:
        cobranca = await mp.criar_cobranca_pix(
            referencia=str(pagamento_id),
            valor=cobrado,
            descricao=f"Contribuição — {c['evento_nome']}",
            # TODO: o MP exige e-mail do pagador; validar se aceita um e-mail genérico por convidado
            email_pagador=f"convidado-{c['id']}@convites.invalid",
        )
    except ErroMercadoPago as e:
        await sessao.rollback()
        logging.getLogger(__name__).error("Falha ao criar PIX: %s", e)
        raise HTTPException(
            502, "Não foi possível gerar o PIX agora. Tente de novo em instantes."
        ) from e

    await sessao.execute(
        text("""
            insert into pagamento (id, convidado_id, tipo, valor_liquido, valor_cobrado, origem,
                                   mp_order_id, mp_payment_id, pix_copia_cola, pix_qr_base64,
                                   expira_em, status)
            values (:id, :convidado_id, 'CONTRIBUICAO', :liquido, :cobrado, 'MERCADO_PAGO',
                    :order_id, :payment_id, :copia_cola, :qr, :expira_em, 'PENDENTE')
        """),
        {
            "id": pagamento_id,
            "convidado_id": c["id"],
            "liquido": liquido,
            "cobrado": cobrado,
            "order_id": cobranca.order_id,
            "payment_id": cobranca.payment_id,
            "copia_cola": cobranca.copia_cola,
            "qr": cobranca.qr_base64,
            "expira_em": expira_em,
        },
    )
    await sessao.commit()
    return PagamentoOut(
        modo="MERCADO_PAGO",
        pagamento_id=pagamento_id,
        valor=cobrado,
        pix_copia_cola=cobranca.copia_cola,
        pix_qr_base64=cobranca.qr_base64,
        expira_em=expira_em,
        status="PENDENTE",
    )


@router.get("/{token}/pagamento/{pagamento_id}/status")
async def status_pagamento(token: str, pagamento_id: UUID, sessao: Sessao) -> dict:
    """Polling da tela de pagamento (RF-PGT-03)."""
    row = (
        (
            await sessao.execute(
                text("""
                select p.status, c.status as convidado_status
                  from pagamento p join convidado c on c.id = p.convidado_id
                 where p.id = :pid and c.token = :token
            """),
                {"pid": pagamento_id, "token": token},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(404, "Pagamento não encontrado")
    return dict(row)
