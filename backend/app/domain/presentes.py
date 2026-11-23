"""Regras da lista de presentes (RF-PRE), sem banco: testadas em tests/test_presentes.py."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum


class ModoPresente(StrEnum):
    RESERVA = "RESERVA"  # o convidado leva o presente
    DINHEIRO = "DINHEIRO"  # o convidado manda um valor no PIX
    AMBOS = "AMBOS"


VALOR_MINIMO = Decimal("1.00")
VALOR_MAXIMO = Decimal("50000.00")


class PresenteIndisponivel(ValueError):
    pass


def aceita_reserva(modo: str) -> bool:
    return modo in (ModoPresente.RESERVA, ModoPresente.AMBOS)


def aceita_dinheiro(modo: str) -> bool:
    return modo in (ModoPresente.DINHEIRO, ModoPresente.AMBOS)


def conferir_reserva(modo: str, reservado_por: object | None, convidado_id: object) -> None:
    """Levanta PresenteIndisponivel se este convidado não puder reservar agora."""
    if not aceita_reserva(modo):
        raise PresenteIndisponivel("Este presente é só em dinheiro")
    if reservado_por is not None and reservado_por != convidado_id:
        raise PresenteIndisponivel("Alguém já escolheu este presente")


def conferir_cancelamento(reservado_por: object | None, convidado_id: object) -> None:
    if reservado_por != convidado_id:
        raise PresenteIndisponivel("Esta reserva não é sua")


def valor_do_presente(bruto: Decimal | str | float) -> Decimal:
    """Valor livre escolhido pelo convidado, em reais com 2 casas (RF-PRE-03)."""
    try:
        valor = Decimal(str(bruto)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as e:
        raise PresenteIndisponivel("Valor inválido") from e
    if valor < VALOR_MINIMO:
        raise PresenteIndisponivel("O valor mínimo é R$ 1,00")
    if valor > VALOR_MAXIMO:
        raise PresenteIndisponivel("Valor acima do permitido")
    return valor


def txid_presente(convidado_id: str) -> str:
    """Identificador no comprovante, diferente do da vaquinha (BORA…): BORAP + 8 hex."""
    return "BORAP" + convidado_id.replace("-", "")[:8].upper()
