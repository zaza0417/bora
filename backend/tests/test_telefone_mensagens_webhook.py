import hashlib
import hmac
import random
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.domain.mensagens import TipoMensagem, formatar_moeda, renderizar
from app.domain.telefone import TelefoneInvalido, normalizar_telefone, para_whatsapp
from app.integrations.mercadopago import validar_assinatura_webhook


# --- telefone ---------------------------------------------------------------
@pytest.mark.parametrize(
    "bruto", ["(11) 98765-4321", "11987654321", "+55 11 98765-4321", "5511987654321"]
)
def test_normaliza_celular(bruto):
    assert normalizar_telefone(bruto if not bruto.startswith("55") else "+" + bruto) == (
        "+5511987654321"
    )


@pytest.mark.parametrize("bruto", ["123", "abc", "(11) 1234"])
def test_telefone_invalido(bruto):
    with pytest.raises(TelefoneInvalido):
        normalizar_telefone(bruto)


def test_para_whatsapp():
    assert para_whatsapp("+5511987654321") == "5511987654321"


# --- mensagens ----------------------------------------------------------------
def test_formatar_moeda():
    assert formatar_moeda(Decimal("30.3")) == "R$ 30,30"
    assert formatar_moeda(Decimal("1234.5")) == "R$ 1.234,50"


def test_renderizar_convite():
    texto = renderizar(
        TipoMensagem.CONVITE,
        {
            "nome": "Ana",
            "evento": "Aniversário",
            "data": datetime(2026, 12, 20, 19, 0),
            "local": "Chácara",
            "link": "https://x/c/abc",
        },
        rng=random.Random(0),
    )
    assert "Ana" in texto and "20/12/2026 às 19h" in texto and "https://x/c/abc" in texto


def test_renderizar_variavel_ausente_nao_quebra():
    texto = renderizar(TipoMensagem.LEMBRETE, {"nome": "Ana", "prazo": date(2026, 12, 7)})
    assert "07/12/2026" in texto


# --- webhook MP -------------------------------------------------------------------
def _assinar(segredo: str, data_id: str, request_id: str, ts: str) -> str:
    manifesto = f"id:{data_id.lower()};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(segredo.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={v1}"


def test_assinatura_valida():
    assinatura = _assinar("segredo", "ORD123", "req-1", "1700000000")
    assert validar_assinatura_webhook(assinatura, "req-1", "ORD123", "segredo")


def test_assinatura_invalida():
    assinatura = _assinar("outro", "ORD123", "req-1", "1700000000")
    assert not validar_assinatura_webhook(assinatura, "req-1", "ORD123", "segredo")
    assert not validar_assinatura_webhook(None, "req-1", "ORD123", "segredo")
    assert not validar_assinatura_webhook(assinatura, "req-1", "ORD123", "")


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("61 9123-4567", "+5561991234567"),  # celular sem o 9 → completa
        ("+556191234567", "+5561991234567"),  # formato do JID antigo do WhatsApp
        ("(11) 8765-4321", "+5511987654321"),
    ],
)
def test_completa_nono_digito(bruto, esperado):
    assert normalizar_telefone(bruto) == esperado


def test_fixo_nao_ganha_nono_digito():
    assert normalizar_telefone("(11) 3333-4444") == "+551133334444"
