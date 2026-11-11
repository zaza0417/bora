"""Cálculo de valores (RF-COL, docs/requisitos.md §3.3)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum

CENTAVO = Decimal("0.01")
REAL = Decimal("1")
TAXA_MP_PADRAO = Decimal("0.0099")


class TipoColaboracao(StrEnum):
    FIXO = "FIXO"
    RATEIO = "RATEIO"


@dataclass(frozen=True)
class Colaboracao:
    tipo: TipoColaboracao
    valor_por_pessoa: Decimal | None = None
    meta: Decimal | None = None
    pessoas_estimadas: int | None = None


def valor_por_pessoa(colab: Colaboracao) -> Decimal:
    """FIXO → valor definido. RATEIO → ceil(meta ÷ pessoas_estimadas) em reais inteiros."""
    if colab.tipo is TipoColaboracao.FIXO:
        if colab.valor_por_pessoa is None or colab.valor_por_pessoa <= 0:
            raise ValueError("Colaboração FIXO exige valor_por_pessoa > 0")
        return colab.valor_por_pessoa.quantize(CENTAVO)

    if (
        not colab.meta
        or colab.meta <= 0
        or not colab.pessoas_estimadas
        or colab.pessoas_estimadas <= 0
    ):
        raise ValueError("Colaboração RATEIO exige meta > 0 e pessoas_estimadas > 0")
    return (
        (colab.meta / colab.pessoas_estimadas)
        .quantize(REAL, rounding=ROUND_CEILING)
        .quantize(CENTAVO)
    )


def soma_por_pessoa(colabs: Iterable[Colaboracao]) -> Decimal:
    return sum((valor_por_pessoa(c) for c in colabs), Decimal("0.00"))


def valor_devido(valor_pessoa: Decimal, qtd_acompanhantes: int) -> Decimal:
    if qtd_acompanhantes < 0:
        raise ValueError("qtd_acompanhantes não pode ser negativa")
    return (valor_pessoa * (1 + qtd_acompanhantes)).quantize(CENTAVO)


def valor_com_taxa(valor_liquido: Decimal, taxa: Decimal = TAXA_MP_PADRAO) -> Decimal:
    """Valor a cobrar para que, descontada a taxa, sobre o valor líquido.

    cobrado = ceil_centavo(liquido ÷ (1 − taxa)).  Ex.: 30,00 → 30,30.
    """
    if not (Decimal("0") <= taxa < Decimal("1")):
        raise ValueError("taxa deve estar em [0, 1)")
    if valor_liquido <= 0:
        raise ValueError("valor_liquido deve ser > 0")
    return (valor_liquido / (1 - taxa)).quantize(CENTAVO, rounding=ROUND_CEILING)
