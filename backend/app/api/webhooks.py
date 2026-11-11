"""Webhooks do Mercado Pago e da Evolution API (RF-PGT-04, RF-MSG-08)."""

from __future__ import annotations

import hmac
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.integrations.evolution import (
    EventoConexao,
    EventoMensagemRecebida,
    interpretar_evento,
)
from app.integrations.mercadopago import validar_assinatura_webhook
from app.services.comprovantes import processar_comprovante
from app.services.pagamentos import processar_order_mp

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])
Sessao = Annotated[AsyncSession, Depends(get_session)]


async def _registrar(sessao: AsyncSession, origem: str, id_externo: str, payload: dict) -> bool:
    """Grava o webhook. Retorna False se já foi recebido antes (idempotência)."""
    res = await sessao.execute(
        text("""
            insert into webhook_recebido (origem, id_externo, payload)
            values (:origem, :id_externo, cast(:payload as jsonb))
            on conflict (origem, id_externo) do nothing
            returning id
        """),
        {"origem": origem, "id_externo": id_externo, "payload": json.dumps(payload)},
    )
    await sessao.commit()
    return res.first() is not None


@router.post("/mercadopago")
async def webhook_mercadopago(
    request: Request,
    sessao: Sessao,
    x_signature: Annotated[str | None, Header()] = None,
    x_request_id: Annotated[str | None, Header()] = None,
) -> dict:
    payload = await request.json()
    data_id = request.query_params.get("data.id") or str((payload.get("data") or {}).get("id", ""))

    if not validar_assinatura_webhook(
        x_signature, x_request_id, data_id, get_settings().mp_webhook_secret
    ):
        raise HTTPException(401, "Assinatura inválida")

    id_externo = x_request_id or f"{payload.get('action')}:{data_id}"
    if not await _registrar(sessao, "MP", id_externo, payload):
        return {"ok": True, "duplicado": True}

    if payload.get("type") == "order" and data_id:
        # Nunca confiar no payload: processar_order_mp consulta a order na API do MP
        await processar_order_mp(sessao, order_id=data_id, mp_user_id=str(payload.get("user_id")))
        await sessao.execute(
            text(
                "update webhook_recebido set processado_em = now() "
                "where origem = 'MP' and id_externo = :id"
            ),
            {"id": id_externo},
        )
        await sessao.commit()
    return {"ok": True}


@router.post("/evolution")
async def webhook_evolution(request: Request, sessao: Sessao) -> dict:
    """Atualiza a conexão da instância e o status de entrega/leitura das mensagens.

    A Evolution envia o cabeçalho x-bora-segredo = EVOLUTION_WEBHOOK_SECRET.
    """
    segredo = get_settings().evolution_webhook_secret
    # Preferência: cabeçalho (não aparece em logs). ?segredo= vale para instâncias antigas.
    recebido = request.headers.get("x-bora-segredo") or request.query_params.get("segredo", "")
    if not segredo or not hmac.compare_digest(recebido, segredo):
        raise HTTPException(401, "Segredo inválido")

    payload = await request.json()
    log.info("evolution webhook: event=%s", payload.get("event"))
    evento = interpretar_evento(payload)
    if evento is None:
        return {"ok": True, "ignorado": True}

    if isinstance(evento, EventoMensagemRecebida):
        # Mensagem enviada por mim só conta no "teste consigo mesmo" (remetente = meu número)
        if evento.de_mim and not await _e_meu_numero(sessao, evento):
            return {"ok": True, "ignorado": True}
        resultado = await processar_comprovante(sessao, evento)
        return {"ok": True, "comprovante": resultado}

    if isinstance(evento, EventoConexao):
        await sessao.execute(
            text("""
                update integracao_whatsapp set status = cast(:st as status_whatsapp)
                 where instancia = :inst
            """),
            {"st": evento.status, "inst": evento.instancia},
        )
    else:
        # Só avança o status (ENVIADA → ENTREGUE → LIDA); nunca volta
        await sessao.execute(
            text("""
                update mensagem set status = cast(:st as status_mensagem)
                 where id_externo = :id
                   and array_position(array['PENDENTE','ENVIADA','ENTREGUE','LIDA']::text[],
                                      status::text)
                     < array_position(array['PENDENTE','ENVIADA','ENTREGUE','LIDA']::text[], :st)
            """),
            {"st": evento.status, "id": evento.id_mensagem},
        )
    await sessao.commit()
    return {"ok": True}


async def _e_meu_numero(sessao: AsyncSession, ev: EventoMensagemRecebida) -> bool:
    row = await sessao.execute(
        text("select numero from integracao_whatsapp where instancia = :i"), {"i": ev.instancia}
    )
    numero = row.scalar()
    return bool(numero) and numero.lstrip("+")[-8:] == ev.remetente[-8:]
