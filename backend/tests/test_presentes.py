from decimal import Decimal

import pytest

from app.domain.presentes import (
    PresenteIndisponivel,
    aceita_dinheiro,
    aceita_reserva,
    conferir_cancelamento,
    conferir_reserva,
    txid_presente,
    valor_do_presente,
)


@pytest.mark.parametrize(
    ("modo", "reserva", "dinheiro"),
    [("RESERVA", True, False), ("DINHEIRO", False, True), ("AMBOS", True, True)],
)
def test_modos(modo, reserva, dinheiro):
    assert aceita_reserva(modo) is reserva
    assert aceita_dinheiro(modo) is dinheiro


def test_reserva_livre_e_propria():
    conferir_reserva("RESERVA", None, "ana")
    conferir_reserva("AMBOS", "ana", "ana")  # reservar de novo o que já é seu não falha


def test_reserva_de_outro_bloqueia():
    with pytest.raises(PresenteIndisponivel, match="já escolheu"):
        conferir_reserva("RESERVA", "bruno", "ana")


def test_presente_so_dinheiro_nao_reserva():
    with pytest.raises(PresenteIndisponivel):
        conferir_reserva("DINHEIRO", None, "ana")


def test_so_quem_reservou_cancela():
    conferir_cancelamento("ana", "ana")
    with pytest.raises(PresenteIndisponivel):
        conferir_cancelamento("bruno", "ana")
    with pytest.raises(PresenteIndisponivel):
        conferir_cancelamento(None, "ana")


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [("50", "50.00"), (Decimal("19.999"), "20.00"), (1, "1.00"), ("123.45", "123.45")],
)
def test_valor_do_presente(bruto, esperado):
    assert valor_do_presente(bruto) == Decimal(esperado)


@pytest.mark.parametrize("bruto", ["0.99", "0", "-5", "abc", "50000.01"])
def test_valor_invalido(bruto):
    with pytest.raises(PresenteIndisponivel):
        valor_do_presente(bruto)


def test_txid_presente_diferente_da_vaquinha():
    assert txid_presente("1a2b3c4d-0000-0000-0000-000000000000") == "BORAP1A2B3C4D"
