from datetime import date

import pytest

from app.domain.prazo import calcular_prazo, eh_dia_util, enesimo_dia_util, prazo_vencido


@pytest.mark.parametrize(
    ("ano", "mes", "esperado"),
    [
        (2026, 12, date(2026, 12, 7)),  # 1(ter) 2 3 4 7
        (2026, 11, date(2026, 11, 9)),  # 2/11 Finados → 3 4 5 6 9
        (2027, 1, date(2027, 1, 8)),  # 1/1 feriado (sex) → 4 5 6 7 8
        (2026, 9, date(2026, 9, 8)),  # 7/9 Independência (seg) → 1 2 3 4 8
    ],
)
def test_quinto_dia_util(ano, mes, esperado):
    assert enesimo_dia_util(ano, mes, 5) == esperado


def test_feriado_nacional_nao_e_dia_util():
    assert not eh_dia_util(date(2026, 11, 2))  # Finados
    assert not eh_dia_util(date(2026, 11, 20))  # Consciência Negra (nacional desde 2024)
    assert eh_dia_util(date(2026, 11, 3))


def test_feriado_estadual_nao_conta():
    # 9/7 (Revolução Constitucionalista) é feriado só em SP → continua dia útil
    assert eh_dia_util(date(2026, 7, 9))


def test_evento_depois_do_d5_usa_d5_do_mesmo_mes():
    assert calcular_prazo(date(2026, 12, 20), hoje=date(2026, 11, 8)) == date(2026, 12, 7)


def test_evento_no_proprio_d5_usa_mes_anterior():
    assert calcular_prazo(date(2026, 12, 7), hoje=date(2026, 10, 1)) == date(2026, 11, 9)


def test_evento_antes_do_d5_usa_mes_anterior():
    assert calcular_prazo(date(2026, 12, 3), hoje=date(2026, 10, 1)) == date(2026, 11, 9)


def test_virada_de_ano():
    # Evento 05/01/2027 (antes do d5 de jan = 08/01) → 5º dia útil de dez/2026
    assert calcular_prazo(date(2027, 1, 5), hoje=date(2026, 11, 8)) == date(2026, 12, 7)


def test_prazo_ja_passou_usa_tres_dias_antes():
    assert calcular_prazo(date(2026, 12, 3), hoje=date(2026, 11, 20)) == date(2026, 11, 30)


def test_prazo_hoje_ainda_vale():
    assert calcular_prazo(date(2026, 12, 20), hoje=date(2026, 12, 7)) == date(2026, 12, 7)


def test_evento_muito_proximo_usa_data_do_evento():
    assert calcular_prazo(date(2026, 12, 3), hoje=date(2026, 12, 2)) == date(2026, 12, 3)


def test_prazo_vencido():
    assert not prazo_vencido(date(2026, 12, 7), hoje=date(2026, 12, 7))
    assert prazo_vencido(date(2026, 12, 7), hoje=date(2026, 12, 8))
