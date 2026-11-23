"""Lista de presentes (RF-PRE).

Convidado (pelo token do link, sem login):
  POST   /convites/{token}/presentes/{id}/reserva  → "Eu levo esse"
  DELETE /convites/{token}/presentes/{id}/reserva  → desiste da reserva
  POST   /convites/{token}/presentes/{id}/pix      → PIX copia-e-cola com o valor escolhido
  POST   /convites/{token}/presentes/{id}/paguei   → avisa que pagou (fica "a conferir")

Organizador:
  GET    /eventos/{id}/presentes                               → reservas e valores
  POST   /eventos/{id}/presentes/pagamentos/{pag}/confirmar    → caiu no extrato
  POST   /eventos/{id}/presentes/pagamentos/{pag}/descartar    → não caiu / engano

O cadastro dos presentes é feito direto no Supabase pelo organizador (RLS), como as
colaborações. O presente em dinheiro não muda a presença do convidado (RF-PRE-04).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.convites import ConviteOut, _carregar, ver_convite
from app.api.organizador import _evento_do_organizador
from app.db import get_session
from app.domain.pix import gerar_copia_cola
from app.domain.presentes import (
    PresenteIndisponivel,
    aceita_dinheiro,
    conferir_cancelamento,
    conferir_reserva,
    txid_presente,
    valor_do_presente,
)
from app.security import OrganizadorAtual
from app.services.presentes import pix_do_organizador, presentes_do_evento

Sessao = Annotated[AsyncSession, Depends(get_session)]
publico = APIRouter(prefix="/convites/{token}/presentes", tags=["convidado"])
organizador = APIRouter(prefix="/eventos/{evento_id}/presentes", tags=["gestão do evento"])


class ValorIn(BaseModel):
    valor: Decimal


class PixPresenteOut(BaseModel):
    valor: Decimal
    pix_copia_cola: str
    pix_chave: str
    pix_nome: str | None


async def _convidado_e_presente(sessao: AsyncSession, token: str, presente_id: UUID):
    c = await _carregar(sessao, token, para_update=True)
    if c["evento_status"] != "ATIVO":
        raise HTTPException(409, "Este evento não está mais recebendo presentes")
    p = (
        (
            await sessao.execute(
                text("""
                select id, modo::text as modo, reservado_por, nome
                  from presente where id = :id and evento_id = :ev
                   for update
            """),
                {"id": presente_id, "ev": c["evento_id"]},
            )
        )
        .mappings()
        .first()
    )
    if p is None:
        raise HTTPException(404, "Presente não encontrado")
    return c, p


def _erro(e: PresenteIndisponivel) -> HTTPException:
    return HTTPException(409, str(e))


# ---------------------------------------------------------------------------
# Convidado
# ---------------------------------------------------------------------------
@publico.post("/{presente_id}/reserva", response_model=ConviteOut)
async def reservar(token: str, presente_id: UUID, sessao: Sessao) -> ConviteOut:
    c, p = await _convidado_e_presente(sessao, token, presente_id)
    try:
        conferir_reserva(p["modo"], p["reservado_por"], c["id"])
    except PresenteIndisponivel as e:
        raise _erro(e) from e
    await sessao.execute(
        text("""
            update presente set reservado_por = :c, reservado_em = coalesce(reservado_em, now())
             where id = :id
        """),
        {"c": c["id"], "id": presente_id},
    )
    await sessao.commit()
    return await ver_convite(token, sessao)


@publico.delete("/{presente_id}/reserva", response_model=ConviteOut)
async def cancelar_reserva(token: str, presente_id: UUID, sessao: Sessao) -> ConviteOut:
    c, p = await _convidado_e_presente(sessao, token, presente_id)
    try:
        conferir_cancelamento(p["reservado_por"], c["id"])
    except PresenteIndisponivel as e:
        raise _erro(e) from e
    await sessao.execute(
        text("update presente set reservado_por = null, reservado_em = null where id = :id"),
        {"id": presente_id},
    )
    await sessao.commit()
    return await ver_convite(token, sessao)


async def _valor_e_pix(sessao: AsyncSession, c, p, bruto: Decimal):
    if not aceita_dinheiro(p["modo"]):
        raise HTTPException(409, "Este presente não recebe dinheiro")
    pix = await pix_do_organizador(sessao, c["organizador_id"])
    if pix is None:
        raise HTTPException(409, "O organizador ainda não cadastrou uma chave PIX")
    try:
        return valor_do_presente(bruto), pix
    except PresenteIndisponivel as e:
        raise _erro(e) from e


@publico.post("/{presente_id}/pix", response_model=PixPresenteOut)
async def pix_presente(token: str, presente_id: UUID, dados: ValorIn, sessao: Sessao):
    c, p = await _convidado_e_presente(sessao, token, presente_id)
    valor, pix = await _valor_e_pix(sessao, c, p, dados.valor)
    await sessao.rollback()  # só leitura: solta o "for update"
    return PixPresenteOut(
        valor=valor,
        pix_copia_cola=gerar_copia_cola(
            chave=pix.chave,
            nome=pix.nome or "Organizador",
            cidade=pix.cidade or "Brasil",
            valor=valor,
            txid=txid_presente(str(c["id"])),
        ),
        pix_chave=pix.chave,
        pix_nome=pix.nome,
    )


@publico.post("/{presente_id}/paguei", response_model=ConviteOut)
async def avisar_pagamento(
    token: str, presente_id: UUID, dados: ValorIn, sessao: Sessao
) -> ConviteOut:
    c, p = await _convidado_e_presente(sessao, token, presente_id)
    valor, _ = await _valor_e_pix(sessao, c, p, dados.valor)
    await sessao.execute(
        text("""
            insert into pagamento (convidado_id, tipo, presente_id, valor_liquido, valor_cobrado,
                                   origem, status, observacao)
            values (:c, 'PRESENTE', :p, :v, :v, 'MANUAL', 'PENDENTE',
                    'Convidado avisou que pagou no PIX')
        """),
        {"c": c["id"], "p": presente_id, "v": valor},
    )
    await sessao.commit()
    return await ver_convite(token, sessao)


# ---------------------------------------------------------------------------
# Organizador
# ---------------------------------------------------------------------------
class PagamentoPresente(BaseModel):
    id: UUID
    convidado_nome: str
    valor: Decimal
    status: str  # PENDENTE (a conferir) | APROVADO
    criado_em: datetime
    pago_em: datetime | None


class PresentePainel(BaseModel):
    id: UUID
    nome: str
    modo: str
    valor_referencia: Decimal | None
    reservado_por_nome: str | None
    reservado_em: datetime | None
    arrecadado: Decimal
    pagamentos: list[PagamentoPresente]


@organizador.get("", response_model=list[PresentePainel])
async def listar(evento_id: UUID, org: OrganizadorAtual, sessao: Sessao) -> list[PresentePainel]:
    await _evento_do_organizador(sessao, evento_id, org.id)
    return [PresentePainel(**p) for p in await presentes_do_evento(sessao, evento_id)]


async def _decidir(sessao: AsyncSession, evento_id: UUID, pagamento_id: UUID, status: str) -> None:
    res = await sessao.execute(
        text("""
            update pagamento pg
               set status = cast(:st as status_pagamento),
                   pago_em = case when cast(:st as status_pagamento) = 'APROVADO'
                                  then now() else null end
              from presente p
             where pg.id = :pag and pg.presente_id = p.id and p.evento_id = :ev
               and pg.tipo = 'PRESENTE' and pg.status = 'PENDENTE'
            returning pg.id
        """),
        {"st": status, "pag": pagamento_id, "ev": evento_id},
    )
    if res.first() is None:
        raise HTTPException(404, "Aviso de pagamento não encontrado ou já conferido")
    await sessao.commit()


@organizador.post("/pagamentos/{pagamento_id}/confirmar", status_code=204)
async def confirmar(evento_id: UUID, pagamento_id: UUID, org: OrganizadorAtual, sessao: Sessao):
    await _evento_do_organizador(sessao, evento_id, org.id)
    await _decidir(sessao, evento_id, pagamento_id, "APROVADO")


@organizador.post("/pagamentos/{pagamento_id}/descartar", status_code=204)
async def descartar(evento_id: UUID, pagamento_id: UUID, org: OrganizadorAtual, sessao: Sessao):
    await _evento_do_organizador(sessao, evento_id, org.id)
    await _decidir(sessao, evento_id, pagamento_id, "CANCELADO")
