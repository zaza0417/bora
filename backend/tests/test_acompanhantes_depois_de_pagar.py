from decimal import Decimal as D

from app.domain.estados import StatusConvidado as S
from app.domain.estados import status_apos_mudar_acompanhantes
from app.domain.valores import falta_pagar, valor_devido


def _mudar(atual, falta, *, pagou=True, vaquinha=True):
    return status_apos_mudar_acompanhantes(
        atual, tem_contribuicao=vaquinha, falta_pagar=D(falta), ja_pagou=pagou
    )


def test_falta_pagar_so_a_diferenca():
    # pagou 30 sozinho, depois disse que leva mais 2 → deve 90, falta 60
    assert falta_pagar(valor_devido(D("30.00"), 2), D("30.00")) == D("60.00")


def test_pagou_a_mais_nao_fica_negativo():
    # pagou 90 com 2 acompanhantes, depois tirou os 2 → deve 30, falta 0
    assert falta_pagar(valor_devido(D("30.00"), 0), D("90.00")) == D("0.00")


def test_nada_pago_falta_tudo():
    assert falta_pagar(D("45.50"), D("0")) == D("45.50")


def test_confirmado_que_aumentou_volta_a_dever():
    assert _mudar(S.CONFIRMADO, "60") is S.AGUARDANDO_PAGAMENTO


def test_confirmado_que_diminuiu_continua_confirmado():
    assert _mudar(S.CONFIRMADO, "0") is S.CONFIRMADO


def test_desistiu_do_aumento_volta_a_confirmado():
    # pagou, aumentou (ficou devendo), voltou ao número já pago
    assert _mudar(S.AGUARDANDO_PAGAMENTO, "0") is S.CONFIRMADO


def test_sem_vaquinha_nao_cobra_nada():
    assert _mudar(S.CONFIRMADO, "60", vaquinha=False) is S.CONFIRMADO


def test_quem_nunca_pagou_segue_o_fluxo_normal():
    for st in (S.CONVIDADO, S.AGUARDANDO_PAGAMENTO, S.RECUSOU):
        assert _mudar(st, "9", pagou=False) is st
