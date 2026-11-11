"""Cálculo do prazo de pagamento (RF-PZ, docs/requisitos.md §3.7).

Regras:
  1. d5 = 5º dia útil do mês do evento.
  2. Se data_evento <= d5 → prazo = 5º dia útil do mês anterior; senão prazo = d5.
  3. Se o prazo calculado já passou (prazo < hoje) → prazo = data_evento − 3 dias corridos.
     Se isso também já passou → prazo = data_evento.

Dia útil = segunda a sexta, exceto feriados nacionais.
"""

from __future__ import annotations

from collections.abc import Container
from datetime import date, timedelta
from functools import lru_cache

import holidays

DIAS_ANTES_FALLBACK = 3


@lru_cache(maxsize=32)
def _feriados_nacionais(ano: int) -> holidays.HolidayBase:
    # Sem subdivisão (estado) → apenas feriados nacionais.
    return holidays.country_holidays("BR", years=ano)


class _FeriadosNacionais:
    """Container que busca os feriados do ano certo sob demanda."""

    def __contains__(self, dia: object) -> bool:
        return isinstance(dia, date) and dia in _feriados_nacionais(dia.year)


FERIADOS_NACIONAIS: Container[date] = _FeriadosNacionais()


def eh_dia_util(dia: date, feriados: Container[date] = FERIADOS_NACIONAIS) -> bool:
    return dia.weekday() < 5 and dia not in feriados


def enesimo_dia_util(
    ano: int, mes: int, n: int = 5, feriados: Container[date] = FERIADOS_NACIONAIS
) -> date:
    dia = date(ano, mes, 1)
    contagem = 0
    while True:
        if eh_dia_util(dia, feriados):
            contagem += 1
            if contagem == n:
                return dia
        dia += timedelta(days=1)


def _mes_anterior(ano: int, mes: int) -> tuple[int, int]:
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


def calcular_prazo(
    data_evento: date, hoje: date, feriados: Container[date] = FERIADOS_NACIONAIS
) -> date:
    d5 = enesimo_dia_util(data_evento.year, data_evento.month, 5, feriados)

    if data_evento <= d5:
        ano, mes = _mes_anterior(data_evento.year, data_evento.month)
        prazo = enesimo_dia_util(ano, mes, 5, feriados)
    else:
        prazo = d5

    if prazo < hoje:
        prazo = data_evento - timedelta(days=DIAS_ANTES_FALLBACK)
        if prazo < hoje:
            prazo = data_evento

    return prazo


def prazo_vencido(prazo: date, hoje: date) -> bool:
    """Prazo vencido = hoje já passou do dia do prazo (o próprio dia do prazo ainda vale)."""
    return hoje > prazo
