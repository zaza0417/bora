"""Cliente do Mercado Pago: OAuth, cobrança PIX (Orders API) e validação de webhook.

Docs:
  * Orders API (PIX): https://www.mercadopago.com.br/developers/pt/docs/checkout-api/overview
  * OAuth:            https://www.mercadopago.com.br/developers/pt/docs/security/oauth
  * Webhooks:         https://www.mercadopago.com.br/developers/pt/docs/your-integrations/notifications/webhooks

TODO (validar antes de produção — ver docs/requisitos.md §9):
  * payload exato da Orders API para PIX e campos de retorno do QR Code;
  * e-mail do pagador: a API exige `payer.email`; o convidado não informa e-mail.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlencode

import httpx

from app.config import get_settings


class ErroMercadoPago(Exception):
    pass


# ---------------------------------------------------------------------------
# Webhook — validação da assinatura (header x-signature: "ts=...,v1=...")
# ---------------------------------------------------------------------------
def validar_assinatura_webhook(
    x_signature: str | None, x_request_id: str | None, data_id: str | None, segredo: str
) -> bool:
    if not (x_signature and segredo):
        return False
    partes = dict(p.strip().split("=", 1) for p in x_signature.split(",") if "=" in p)
    ts, v1 = partes.get("ts"), partes.get("v1")
    if not (ts and v1):
        return False

    manifesto = ""
    if data_id:
        # Ids alfanuméricos devem ir em minúsculas no manifesto
        manifesto += f"id:{data_id.lower()};"
    if x_request_id:
        manifesto += f"request-id:{x_request_id};"
    manifesto += f"ts:{ts};"

    esperado = hmac.new(segredo.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, v1)


# ---------------------------------------------------------------------------
# OAuth — conectar a conta do organizador
# ---------------------------------------------------------------------------
def url_autorizacao(state: str, redirect_uri: str) -> str:
    s = get_settings()
    query = urlencode(
        {
            "client_id": s.mp_client_id,
            "response_type": "code",
            "platform_id": "mp",
            "state": state,
            "redirect_uri": redirect_uri,
        }
    )
    return f"{s.mp_auth_base.rstrip('/')}/authorization?{query}"


async def trocar_code_por_token(code: str, redirect_uri: str) -> dict:
    return await _oauth_token(
        {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}
    )


async def renovar_token(refresh_token: str) -> dict:
    return await _oauth_token({"grant_type": "refresh_token", "refresh_token": refresh_token})


async def _oauth_token(dados: dict) -> dict:
    s = get_settings()
    async with httpx.AsyncClient(timeout=20) as cli:
        r = await cli.post(
            f"{s.mp_api_base}/oauth/token",
            data={"client_id": s.mp_client_id, "client_secret": s.mp_client_secret, **dados},
        )
    if r.status_code >= 400:
        raise ErroMercadoPago(f"OAuth falhou: {r.status_code} {r.text[:500]}")
    # Resposta: access_token, refresh_token, public_key, user_id, expires_in (segundos)
    return r.json()


# ---------------------------------------------------------------------------
# Cobrança PIX — usa o access_token DO ORGANIZADOR (dinheiro cai na conta dele)
# ---------------------------------------------------------------------------
@dataclass
class CobrancaPix:
    order_id: str
    payment_id: str | None
    status: str
    copia_cola: str | None
    qr_base64: str | None


@dataclass
class MercadoPagoClient:
    access_token: str
    base_url: str = "https://api.mercadopago.com"
    timeout: float = 20.0

    async def _req(
        self, metodo: str, caminho: str, json: dict | None = None, idem: str | None = None
    ) -> dict:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if idem:
            headers["X-Idempotency-Key"] = idem
        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            r = await cli.request(metodo, f"{self.base_url}{caminho}", json=json, headers=headers)
        if r.status_code >= 400:
            raise ErroMercadoPago(f"{metodo} {caminho} → {r.status_code}: {r.text[:500]}")
        return r.json()

    async def criar_cobranca_pix(
        self,
        *,
        referencia: str,
        valor: Decimal,
        descricao: str,
        email_pagador: str,
        expiracao_iso8601: str = "P1D",
    ) -> CobrancaPix:
        """Cria uma order com pagamento PIX. `referencia` = id do pagamento interno."""
        corpo = {
            "type": "online",
            "external_reference": referencia,
            "description": descricao[:255],
            "total_amount": f"{valor:.2f}",
            "processing_mode": "automatic",
            "payer": {"email": email_pagador},
            "transactions": {
                "payments": [
                    {
                        "amount": f"{valor:.2f}",
                        "payment_method": {"id": "pix", "type": "bank_transfer"},
                        "expiration_time": expiracao_iso8601,
                    }
                ]
            },
        }
        dados = await self._req("POST", "/v1/orders", corpo, idem=referencia)
        return _parse_order(dados)

    async def consultar_order(self, order_id: str) -> CobrancaPix:
        return _parse_order(await self._req("GET", f"/v1/orders/{order_id}"))

    async def cancelar_order(self, order_id: str) -> None:
        await self._req("POST", f"/v1/orders/{order_id}/cancel", idem=f"cancel-{order_id}")


def _parse_order(dados: dict) -> CobrancaPix:
    pagamentos = (dados.get("transactions") or {}).get("payments") or [{}]
    pag = pagamentos[0]
    metodo = pag.get("payment_method") or {}
    return CobrancaPix(
        order_id=str(dados.get("id")),
        payment_id=str(pag["id"]) if pag.get("id") else None,
        status=str(dados.get("status")),
        copia_cola=metodo.get("qr_code"),
        qr_base64=metodo.get("qr_code_base64"),
    )
