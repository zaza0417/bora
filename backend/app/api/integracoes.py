"""Conexão do organizador com Mercado Pago (OAuth) e WhatsApp (Evolution API) — RF-ORG-02..05.

Mercado Pago
  GET    /integracoes/mercadopago/autorizar  → URL de autorização (front redireciona)
  GET    /integracoes/mercadopago/callback   → MP volta aqui com ?code&state; salva tokens
  DELETE /integracoes/mercadopago            → desconecta

WhatsApp
  POST   /integracoes/whatsapp/conectar      → cria/reabre a instância e devolve o QR Code
  GET    /integracoes/whatsapp/status        → estado atual (+ QR enquanto não conecta)
  DELETE /integracoes/whatsapp               → desconecta o número
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.integrations import mercadopago as mp
from app.integrations.evolution import ErroEvolution, EvolutionClient
from app.security import (
    OrganizadorAtual,
    criptografar,
    gerar_state_oauth,
    validar_state_oauth,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/integracoes", tags=["integrações"])
Sessao = Annotated[AsyncSession, Depends(get_session)]


# ---------------------------------------------------------------------------
# Mercado Pago
# ---------------------------------------------------------------------------
class UrlOut(BaseModel):
    url: str


@router.get("/mercadopago/autorizar", response_model=UrlOut)
async def mp_autorizar(org: OrganizadorAtual) -> UrlOut:
    s = get_settings()
    if not s.mp_client_id:
        raise HTTPException(503, "Mercado Pago não configurado no servidor (MP_CLIENT_ID)")
    return UrlOut(url=mp.url_autorizacao(gerar_state_oauth(org.id), s.mp_redirect_uri))


def _voltar_ao_front(**params: str) -> RedirectResponse:
    base = get_settings().url_publica_front.rstrip("/")
    return RedirectResponse(f"{base}/configuracoes?{urlencode(params)}", status_code=302)


async def salvar_tokens_mp(sessao: AsyncSession, organizador_id: UUID, dados: dict) -> None:
    """Grava/atualiza a integração com os tokens criptografados."""
    expira_em = datetime.now(UTC) + timedelta(seconds=int(dados.get("expires_in", 15552000)))
    await sessao.execute(
        text("""
            insert into integracao_mp (organizador_id, mp_user_id, access_token_enc,
                                       refresh_token_enc, public_key, expira_em, status)
            values (:org, :uid, :at, :rt, :pk, :exp, 'ATIVA')
            on conflict (organizador_id) do update
               set mp_user_id = excluded.mp_user_id,
                   access_token_enc = excluded.access_token_enc,
                   refresh_token_enc = excluded.refresh_token_enc,
                   public_key = excluded.public_key,
                   expira_em = excluded.expira_em,
                   status = 'ATIVA'
        """),
        {
            "org": organizador_id,
            "uid": str(dados["user_id"]),
            "at": criptografar(dados["access_token"]),
            "rt": criptografar(dados["refresh_token"]),
            "pk": dados.get("public_key"),
            "exp": expira_em,
        },
    )


@router.get("/mercadopago/callback", include_in_schema=False)
async def mp_callback(
    sessao: Sessao, code: str | None = None, state: str | None = None, error: str | None = None
) -> RedirectResponse:
    """Sem JWT: quem chega aqui é o navegador vindo do MP. O organizador vem no `state`."""
    if error or not code or not state:
        return _voltar_ao_front(mp="erro", motivo=error or "autorizacao_cancelada")
    try:
        org_id = validar_state_oauth(state)
    except ValueError:
        return _voltar_ao_front(mp="erro", motivo="link_expirado")
    try:
        dados = await mp.trocar_code_por_token(code, get_settings().mp_redirect_uri)
    except mp.ErroMercadoPago as e:
        log.error("OAuth MP falhou: %s", e)
        return _voltar_ao_front(mp="erro", motivo="falha_mercado_pago")

    await salvar_tokens_mp(sessao, org_id, dados)
    await sessao.commit()
    return _voltar_ao_front(mp="ok")


@router.delete("/mercadopago", status_code=204)
async def mp_desconectar(org: OrganizadorAtual, sessao: Sessao) -> None:
    await sessao.execute(
        text("delete from integracao_mp where organizador_id = :org"), {"org": org.id}
    )
    await sessao.commit()


# ---------------------------------------------------------------------------
# WhatsApp (Evolution)
# ---------------------------------------------------------------------------
class WhatsappOut(BaseModel):
    status: str  # CONECTADO | DESCONECTADO | AGUARDANDO_QR | NAO_CONFIGURADO
    numero: str | None = None
    qr_base64: str | None = None


ESTADO_EVOLUTION = {"open": "CONECTADO", "connecting": "AGUARDANDO_QR", "close": "DESCONECTADO"}


def nome_instancia(organizador_id: UUID) -> str:
    return f"bora-{organizador_id.hex[:12]}"


def url_webhook_evolution() -> str:
    s = get_settings()
    base = (s.evolution_webhook_base or s.url_publica_api).rstrip("/")
    return f"{base}/webhooks/evolution"


def _qr(dados: dict) -> str | None:
    """A Evolution devolve o QR como data URL ('data:image/png;base64,...') em 'base64'."""
    qr = dados.get("base64") or (dados.get("qrcode") or {}).get("base64")
    if qr and "," in qr:
        qr = qr.split(",", 1)[1]
    return qr


async def _gravar_whatsapp(
    sessao: AsyncSession, org_id: UUID, instancia: str, status: str, numero: str | None = None
) -> None:
    await sessao.execute(
        text("""
            insert into integracao_whatsapp (organizador_id, instancia, status, numero)
            values (:org, :inst, cast(:st as status_whatsapp), :num)
            on conflict (organizador_id) do update
               set instancia = excluded.instancia, status = excluded.status,
                   numero = coalesce(excluded.numero, integracao_whatsapp.numero)
        """),
        {"org": org_id, "inst": instancia, "st": status, "num": numero},
    )


@router.post("/whatsapp/conectar", response_model=WhatsappOut)
async def whatsapp_conectar(org: OrganizadorAtual, sessao: Sessao) -> WhatsappOut:
    s = get_settings()
    if not s.evolution_api_key:
        raise HTTPException(503, "WhatsApp não configurado no servidor (EVOLUTION_API_KEY)")
    evo = EvolutionClient.from_settings()
    instancia = nome_instancia(org.id)
    try:
        try:
            dados = await evo.criar_instancia(
                instancia, url_webhook_evolution(), {"x-bora-segredo": s.evolution_webhook_secret}
            )
        except ErroEvolution as e:
            if "already" not in str(e).lower() and "403" not in str(e):
                raise
            dados = await evo.qrcode(instancia)  # instância já existe → só pede novo QR
    except ErroEvolution as e:
        log.error("Evolution falhou: %s", e)
        raise HTTPException(502, "Não foi possível falar com o serviço de WhatsApp") from e

    await _gravar_whatsapp(sessao, org.id, instancia, "AGUARDANDO_QR")
    await sessao.commit()
    return WhatsappOut(status="AGUARDANDO_QR", qr_base64=_qr(dados))


@router.get("/whatsapp/status", response_model=WhatsappOut)
async def whatsapp_status(org: OrganizadorAtual, sessao: Sessao) -> WhatsappOut:
    row = (
        (
            await sessao.execute(
                text(
                    "select instancia, status::text as status, numero from integracao_whatsapp "
                    "where organizador_id = :org"
                ),
                {"org": org.id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return WhatsappOut(status="NAO_CONFIGURADO")

    evo = EvolutionClient.from_settings()
    try:
        estado = ESTADO_EVOLUTION.get(await evo.estado(row["instancia"]), "DESCONECTADO")
    except ErroEvolution:
        return WhatsappOut(status=row["status"], numero=row["numero"])

    qr = None
    if estado == "AGUARDANDO_QR":
        try:
            qr = _qr(await evo.qrcode(row["instancia"]))
        except ErroEvolution:
            qr = None
    numero = row["numero"]
    if estado == "CONECTADO" and not numero:
        numero = await evo.numero_conectado(row["instancia"])
    if estado != row["status"] or numero != row["numero"]:
        await _gravar_whatsapp(sessao, org.id, row["instancia"], estado, numero)
        await sessao.commit()
    return WhatsappOut(status=estado, numero=numero, qr_base64=qr)


@router.delete("/whatsapp", status_code=204)
async def whatsapp_desconectar(org: OrganizadorAtual, sessao: Sessao) -> None:
    row = (
        await sessao.execute(
            text("select instancia from integracao_whatsapp where organizador_id = :org"),
            {"org": org.id},
        )
    ).first()
    if row is None:
        return
    evo = EvolutionClient.from_settings()
    try:
        await evo.desconectar(row[0])
    except ErroEvolution as e:
        log.warning("Falha ao desconectar instância %s: %s", row[0], e)
    await sessao.execute(
        text("delete from integracao_whatsapp where organizador_id = :org"), {"org": org.id}
    )
    await sessao.commit()
