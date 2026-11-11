"""Simulador LOCAL do Mercado Pago — para testar o fluxo sem credenciais reais.

Imita só o que o Bora usa:
  GET  /authorization         tela de "autorizar" do OAuth → volta para redirect_uri?code=...
  POST /oauth/token           troca code/refresh_token por tokens falsos
  POST /v1/orders             cria order PIX (QR falso)
  GET  /v1/orders/{id}        consulta
  POST /v1/orders/{id}/cancel cancela
  GET  /simular               página com as cobranças e botões "Pagar" / "Expirar"
  POST /simular/{id}/{acao}   muda o status e envia o webhook ASSINADO para o Bora

Rodar (porta 8090):  uv run uvicorn scripts.mock_mercadopago:app --port 8090
No backend/.env:     MP_API_BASE=http://localhost:8090  e  MP_AUTH_BASE=http://localhost:8090

NUNCA use em produção. Os formatos seguem o que o código do Bora espera
(app/integrations/mercadopago.py); quando o MP real responder diferente, ajuste os dois.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import os
import secrets
import time
from urllib.parse import parse_qs, urlencode

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="Mercado Pago (simulador local)")

from app.config import get_settings  # noqa: E402 — lê o mesmo backend/.env da API

WEBHOOK_URL = os.environ.get("MOCK_WEBHOOK_URL", "http://localhost:8000/webhooks/mercadopago")
WEBHOOK_SECRET = get_settings().mp_webhook_secret  # assina igual ao MP real
USER_ID = 123456789  # "conta" do organizador no simulador

# 1x1 cinza — o QR é falso; o que importa é o fluxo
QR_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="

tokens_validos: set[str] = set()
orders: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------
@app.get("/authorization", response_class=HTMLResponse)
async def autorizar(redirect_uri: str, state: str, client_id: str = "") -> str:
    code = "MOCK-CODE-" + secrets.token_hex(6)
    ok = f"{redirect_uri}?{urlencode({'code': code, 'state': state})}"
    negar = f"{redirect_uri}?{urlencode({'error': 'access_denied', 'state': state})}"
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width">
    <body style="font-family:system-ui;max-width:420px;margin:3rem auto;padding:1rem">
    <h2>🟦 Mercado Pago <small>(simulador local)</small></h2>
    <p>A aplicação <b>{html.escape(client_id or "Bora")}</b> quer receber pagamentos na sua conta.</p>
    <p><a href="{html.escape(ok)}" style="background:#009ee3;color:#fff;padding:.7rem 1.2rem;
      border-radius:8px;text-decoration:none">Autorizar</a>
    &nbsp; <a href="{html.escape(negar)}">Cancelar</a></p></body>"""


@app.post("/oauth/token")
async def token(request: Request):
    # O Bora manda application/x-www-form-urlencoded (como o MP real espera)
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
    grant_type, code, refresh_token = (
        form.get("grant_type"),
        form.get("code"),
        form.get("refresh_token"),
    )
    if grant_type == "authorization_code" and not (code or "").startswith("MOCK-CODE-"):
        raise HTTPException(400, {"error": "invalid_grant"})
    if grant_type == "refresh_token" and not (refresh_token or "").startswith("MOCK-RT-"):
        raise HTTPException(400, {"error": "invalid_grant"})
    at = "MOCK-AT-" + secrets.token_hex(8)
    tokens_validos.add(at)
    return {
        "access_token": at,
        "refresh_token": "MOCK-RT-" + secrets.token_hex(8),
        "public_key": "MOCK-PK",
        "user_id": USER_ID,
        "expires_in": 15552000,
        "token_type": "Bearer",
    }


def _exigir_token(authorization: str | None) -> None:
    tok = (authorization or "").removeprefix("Bearer ").strip()
    # Tokens emitidos antes de reiniciar o simulador continuam valendo se tiverem o prefixo
    if not tok.startswith("MOCK-AT-"):
        raise HTTPException(401, {"message": "invalid access token"})


# ---------------------------------------------------------------------------
# Orders API
# ---------------------------------------------------------------------------
@app.post("/v1/orders")
async def criar_order(
    request: Request,
    authorization: str | None = Header(None),
    x_idempotency_key: str | None = Header(None),
):
    _exigir_token(authorization)
    if not x_idempotency_key:
        raise HTTPException(400, {"message": "X-Idempotency-Key is required"})
    for o in orders.values():  # idempotência
        if o["_idem"] == x_idempotency_key:
            return o["dados"]
    corpo = await request.json()
    pag = corpo["transactions"]["payments"][0]
    if pag["payment_method"] != {"id": "pix", "type": "bank_transfer"}:
        raise HTTPException(400, {"message": "unsupported payment method"})
    if not (corpo.get("payer") or {}).get("email"):
        raise HTTPException(400, {"message": "payer.email is required"})

    oid = "ORD" + secrets.token_hex(6).upper()
    dados = {
        "id": oid,
        "status": "action_required",
        "external_reference": corpo.get("external_reference"),
        "total_amount": corpo["total_amount"],
        "description": corpo.get("description"),
        "transactions": {
            "payments": [
                {
                    "id": "PAY" + secrets.token_hex(6).upper(),
                    "amount": pag["amount"],
                    "status": "action_required",
                    "payment_method": {
                        "id": "pix",
                        "type": "bank_transfer",
                        "qr_code": f"00020101021226MOCKPIX{oid}5204000053039865406{pag['amount']}",
                        "qr_code_base64": QR_PNG,
                    },
                }
            ]
        },
    }
    orders[oid] = {"_idem": x_idempotency_key, "dados": dados}
    return dados


@app.get("/v1/orders/{oid}")
async def ver_order(oid: str, authorization: str | None = Header(None)):
    _exigir_token(authorization)
    if oid not in orders:
        raise HTTPException(404, {"message": "order not found"})
    return orders[oid]["dados"]


@app.post("/v1/orders/{oid}/cancel")
async def cancelar_order(oid: str, authorization: str | None = Header(None)):
    _exigir_token(authorization)
    if oid not in orders:
        raise HTTPException(404, {"message": "order not found"})
    orders[oid]["dados"]["status"] = "canceled"
    return orders[oid]["dados"]


# ---------------------------------------------------------------------------
# Simulação de pagamento + webhook assinado (mesmo esquema do MP real)
# ---------------------------------------------------------------------------
async def _enviar_webhook(oid: str, acao: str) -> int:
    request_id = secrets.token_hex(8)
    ts = str(int(time.time()))
    manifesto = f"id:{oid.lower()};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(WEBHOOK_SECRET.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
    async with httpx.AsyncClient(timeout=20) as cli:
        r = await cli.post(
            f"{WEBHOOK_URL}?data.id={oid}&type=order",
            json={"type": "order", "action": acao, "data": {"id": oid}, "user_id": USER_ID},
            headers={"x-signature": f"ts={ts},v1={v1}", "x-request-id": request_id},
        )
    return r.status_code


ACOES = {
    "pagar": ("processed", "order.processed"),
    "expirar": ("expired", "order.expired"),
    "estornar": ("refunded", "order.refunded"),
}


@app.post("/simular/{oid}/{acao}")
async def simular(oid: str, acao: str):
    if oid not in orders or acao not in ACOES:
        raise HTTPException(404, "order ou ação desconhecida")
    status, evento = ACOES[acao]
    orders[oid]["dados"]["status"] = status
    orders[oid]["dados"]["transactions"]["payments"][0]["status"] = status
    codigo = await _enviar_webhook(oid, evento)
    return RedirectResponse(f"/simular?ultimo={oid}:{acao}:{codigo}", status_code=303)


@app.get("/simular", response_class=HTMLResponse)
async def painel(ultimo: str | None = None) -> str:
    linhas = (
        "".join(
            f"""<tr><td>{oid}</td><td>R$ {o["dados"]["total_amount"]}</td>
        <td>{html.escape(o["dados"].get("description") or "")}</td><td><b>{
                o["dados"]["status"]
            }</b></td>
        <td>{
                "".join(
                    f'<form method=post action="/simular/{oid}/{a}" style="display:inline">'
                    f"<button>{a.capitalize()}</button></form> "
                    for a in ACOES
                )
            }</td></tr>"""
            for oid, o in reversed(list(orders.items()))
        )
        or "<tr><td colspan=5>Nenhuma cobrança ainda — gere um PIX na página do convidado.</td></tr>"
    )
    aviso = ""
    if ultimo:
        oid, acao, codigo = ultimo.split(":")
        aviso = f"<p>Ação <b>{acao}</b> em {oid}: webhook respondeu <b>HTTP {codigo}</b>.</p>"
    return f"""<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=5>
    <body style="font-family:system-ui;margin:2rem"><h2>🟦 Simulador do Mercado Pago</h2>{aviso}
    <table border=1 cellpadding=6 style="border-collapse:collapse">
    <tr><th>Order</th><th>Valor</th><th>Descrição</th><th>Status</th><th>Simular</th></tr>
    {linhas}</table><p><small>Atualiza a cada 5 s. Webhook → {html.escape(WEBHOOK_URL)}</small></p>"""
