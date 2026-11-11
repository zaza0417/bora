"""Cria uma order PIX de TESTE na API REAL do Mercado Pago (credenciais de teste).

Serve para:
  * obter o "Order ID" pedido no painel do MP (Processo de integração → Medir a qualidade);
  * validar que o payload do Bora (app/integrations/mercadopago.py) é aceito pelo MP real.

Uso (na pasta backend):
  1. No backend/.env, adicione:  MP_ACCESS_TOKEN_TESTE=TEST-....   (Credenciais de teste)
  2. uv run python scripts/mp_order_teste.py

Não movimenta dinheiro: com credencial de teste o PIX não é cobrado de verdade.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations.mercadopago import ErroMercadoPago, MercadoPagoClient  # noqa: E402


def _ler_token() -> str:
    token = os.environ.get("MP_ACCESS_TOKEN_TESTE")
    if not token:
        env = Path(__file__).resolve().parents[1] / ".env"
        for linha in env.read_text(encoding="utf-8").splitlines():
            if linha.startswith("MP_ACCESS_TOKEN_TESTE="):
                token = linha.split("=", 1)[1].strip()
    if not token:
        sys.exit("Faltou MP_ACCESS_TOKEN_TESTE no backend/.env (Credenciais de teste → Access Token)")
    return token


async def main() -> None:
    token = _ler_token()
    # Token de teste pode começar com TEST- ou APP_USR- (conta vendedora de teste criada pelo MP)
    print(f"Usando token que começa com {token[:8]}…")
    mp = MercadoPagoClient(access_token=token, base_url="https://api.mercadopago.com")
    referencia = str(uuid.uuid4())
    try:
        cobranca = await mp.criar_cobranca_pix(
            referencia=referencia,
            valor=Decimal("30.30"),
            descricao="Contribuição — Evento de teste do Bora",
            email_pagador="test_user_bora@testuser.com",
        )
    except ErroMercadoPago as e:
        print("\nO Mercado Pago recusou o pedido:\n ", e)
        print("\nCopie essa mensagem para o Claude ajustar o payload.")
        sys.exit(1)

    print("\nOrder criada no Mercado Pago ✅")
    print(f"  Order ID ........ {cobranca.order_id}   ← cole no painel do MP")
    print(f"  Status .......... {cobranca.status}")
    print(f"  Payment ID ...... {cobranca.payment_id}")
    print(f"  PIX copia/cola .. {'sim' if cobranca.copia_cola else 'NÃO veio'}")
    print(f"  QR base64 ....... {'sim' if cobranca.qr_base64 else 'NÃO veio'}")
    print(f"  external_ref .... {referencia}")


if __name__ == "__main__":
    asyncio.run(main())
