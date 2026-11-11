"""Endpoints do organizador (autenticado via JWT do Supabase).

O CRUD simples (evento, atrações, cardápio, colaborações, presentes) pode ser feito
direto pelo Angular via Supabase + RLS. Aqui ficam as operações com regra de negócio:
ativar evento (calcula prazo), cadastrar convidado (token, snapshot, convite).
O restante da gestão (convidados, painel, cancelamento) está em app/api/gestao.py.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.domain.mensagens import TipoMensagem
from app.domain.prazo import calcular_prazo
from app.domain.telefone import TelefoneInvalido, normalizar_telefone
from app.domain.valores import Colaboracao, TipoColaboracao, valor_por_pessoa
from app.security import OrganizadorAtual, gerar_token_convite
from app.services.cobranca import modo_pagamento
from app.services.mensageria import enfileirar_mensagem

router = APIRouter(tags=["organizador"])
Sessao = Annotated[AsyncSession, Depends(get_session)]


class EuOut(BaseModel):
    id: UUID
    email: str | None
    mercado_pago_conectado: bool
    whatsapp_status: str | None


class ConvidadoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    telefone: str = Field(min_length=8, max_length=30)


class ConvidadoOut(BaseModel):
    id: UUID
    nome: str
    telefone_e164: str
    status: str
    valor_por_pessoa: Decimal
    link: str


async def _evento_do_organizador(sessao: AsyncSession, evento_id: UUID, org_id: UUID):
    ev = (
        (
            await sessao.execute(
                text("select * from evento where id = :id and organizador_id = :org"),
                {"id": evento_id, "org": org_id},
            )
        )
        .mappings()
        .first()
    )
    if ev is None:
        raise HTTPException(404, "Evento não encontrado")
    return ev


@router.get("/eu", response_model=EuOut)
async def eu(org: OrganizadorAtual, sessao: Sessao) -> EuOut:
    row = (
        (
            await sessao.execute(
                text("""
                select exists(select 1 from integracao_mp m
                               where m.organizador_id = :id and m.status = 'ATIVA') as mp,
                       (select w.status::text from integracao_whatsapp w
                         where w.organizador_id = :id) as wa
            """),
                {"id": org.id},
            )
        )
        .mappings()
        .one()
    )
    return EuOut(
        id=org.id, email=org.email, mercado_pago_conectado=row["mp"], whatsapp_status=row["wa"]
    )


@router.post("/eventos/{evento_id}/ativar")
async def ativar_evento(evento_id: UUID, org: OrganizadorAtual, sessao: Sessao) -> dict:
    """RASCUNHO → ATIVO: calcula o prazo (se não for manual) e enfileira os convites pendentes."""
    ev = await _evento_do_organizador(sessao, evento_id, org.id)
    if ev["status"] != "RASCUNHO":
        raise HTTPException(409, f"Evento está {ev['status']}")

    if ev["tem_contribuicao"]:
        modo = await modo_pagamento(sessao, org.id)
        if modo.modo == "NENHUM":
            raise HTTPException(
                409,
                "Cadastre sua chave PIX em Configurações (ou conecte o Mercado Pago) "
                "antes de ativar um evento com contribuição",
            )
        if modo.modo == "PIX_MANUAL" and not modo.whatsapp_numero:
            raise HTTPException(
                409, "Conecte o WhatsApp (ou informe seu telefone) para receber os comprovantes"
            )

    fuso = ZoneInfo(get_settings().fuso)
    prazo = ev["prazo_pagamento"]
    if ev["tem_contribuicao"] and not ev["prazo_manual"]:
        prazo = calcular_prazo(ev["data_hora"].astimezone(fuso).date(), datetime.now(fuso).date())

    await sessao.execute(
        text("update evento set status = 'ATIVO', prazo_pagamento = :prazo where id = :id"),
        {"prazo": prazo, "id": evento_id},
    )
    pendentes = (
        (
            await sessao.execute(
                text("""
                select c.id from convidado c
                 where c.evento_id = :id
                   and not exists (select 1 from mensagem m
                                    where m.convidado_id = c.id and m.tipo = 'CONVITE')
            """),
                {"id": evento_id},
            )
        )
        .scalars()
        .all()
    )
    for convidado_id in pendentes:
        await enfileirar_mensagem(sessao, convidado_id, TipoMensagem.CONVITE)
    await sessao.commit()
    return {"status": "ATIVO", "prazo_pagamento": prazo, "convites_enfileirados": len(pendentes)}


@router.post("/eventos/{evento_id}/convidados", response_model=ConvidadoOut, status_code=201)
async def adicionar_convidado(
    evento_id: UUID, dados: ConvidadoIn, org: OrganizadorAtual, sessao: Sessao
) -> ConvidadoOut:
    ev = await _evento_do_organizador(sessao, evento_id, org.id)
    if ev["status"] in ("CANCELADO", "ENCERRADO"):
        raise HTTPException(409, f"Evento está {ev['status']}")
    try:
        telefone = normalizar_telefone(dados.telefone)
    except TelefoneInvalido as e:
        raise HTTPException(422, str(e)) from e

    # Snapshot do valor por pessoa de cada colaboração (RF-COL-04)
    colabs = (
        (
            await sessao.execute(
                text("""
                select id, tipo, valor_por_pessoa, meta, pessoas_estimadas
                  from colaboracao where evento_id = :id
            """),
                {"id": evento_id},
            )
        )
        .mappings()
        .all()
    )
    snapshot = (
        {
            c["id"]: valor_por_pessoa(
                Colaboracao(
                    tipo=TipoColaboracao(c["tipo"]),
                    valor_por_pessoa=c["valor_por_pessoa"],
                    meta=c["meta"],
                    pessoas_estimadas=c["pessoas_estimadas"],
                )
            )
            for c in colabs
        }
        if ev["tem_contribuicao"]
        else {}
    )
    total = sum(snapshot.values(), Decimal("0.00"))
    token = gerar_token_convite()

    try:
        convidado_id = (
            await sessao.execute(
                text("""
                    insert into convidado (evento_id, nome, telefone_e164, token, valor_por_pessoa)
                    values (:ev, :nome, :tel, :token, :vpp)
                    returning id
                """),
                {
                    "ev": evento_id,
                    "nome": dados.nome.strip(),
                    "tel": telefone,
                    "token": token,
                    "vpp": total,
                },
            )
        ).scalar_one()
    except IntegrityError as e:
        await sessao.rollback()
        raise HTTPException(409, "Este telefone já está na lista do evento") from e

    for colab_id, valor in snapshot.items():
        await sessao.execute(
            text("""
                insert into convidado_colaboracao (convidado_id, colaboracao_id, valor_por_pessoa)
                values (:c, :col, :v)
            """),
            {"c": convidado_id, "col": colab_id, "v": valor},
        )

    if ev["status"] == "ATIVO":  # RF-CNV-05: convite sai na hora
        await enfileirar_mensagem(sessao, convidado_id, TipoMensagem.CONVITE)
    await sessao.commit()

    return ConvidadoOut(
        id=convidado_id,
        nome=dados.nome.strip(),
        telefone_e164=telefone,
        status="CONVIDADO",
        valor_por_pessoa=total,
        link=f"{get_settings().url_publica_front.rstrip('/')}/c/{token}",
    )
