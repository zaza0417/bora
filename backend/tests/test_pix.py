from decimal import Decimal

import pytest

from app.domain.pix import crc16_ccitt, gerar_copia_cola, txid_do_convidado


def test_crc16_vetor_classico():
    # Vetor padrão do CRC-16/CCITT-FALSE
    assert crc16_ccitt("123456789") == "29B1"


def test_gera_payload_com_valor_e_txid():
    p = gerar_copia_cola(
        chave="isac@exemplo.com",
        nome="Isac Carmo",
        cidade="Brasília",
        valor=Decimal("30"),
        txid="BORA12AB34CD",
    )
    assert p.startswith("000201")
    assert "0014br.gov.bcb.pix0116isac@exemplo.com" in p
    assert "540530.00" in p  # valor com 2 casas
    assert "5910Isac Carmo" in p
    assert "6008Brasilia" in p  # sem acento
    assert "62160512BORA12AB34CD" in p
    assert p[-8:-4] == "6304" and p[-4:] == crc16_ccitt(p[:-4])


def test_sem_valor_e_sem_txid():
    p = gerar_copia_cola("+5561999999999", "Ana", "Goiania")
    assert "54" not in p[:20] and "62070503***" in p


def test_nome_e_cidade_sao_cortados():
    p = gerar_copia_cola(
        "chave", "Nome Muito Comprido Que Passa Do Limite", "Cidade Comprida Demais"
    )
    assert "5925Nome Muito Comprido Que P" in p
    assert "6015Cidade Comprida" in p


@pytest.mark.parametrize("valor", [Decimal("0"), Decimal("-1")])
def test_valor_invalido(valor):
    with pytest.raises(ValueError):
        gerar_copia_cola("chave", "Nome", "Cidade", valor)


def test_txid_do_convidado():
    t = txid_do_convidado("46ab551a-771e-4d54-b635-75afb91e15ec")
    assert t == "BORA46AB551A" and len(t) <= 25
