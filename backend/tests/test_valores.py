from decimal import Decimal as D

import pytest

from app.domain.valores import (
    Colaboracao,
    TipoColaboracao,
    soma_por_pessoa,
    valor_com_taxa,
    valor_devido,
    valor_por_pessoa,
)


def test_fixo():
    c = Colaboracao(TipoColaboracao.FIXO, valor_por_pessoa=D("30"))
    assert valor_por_pessoa(c) == D("30.00")


def test_rateio_arredonda_para_cima_em_reais():
    c = Colaboracao(TipoColaboracao.RATEIO, meta=D("800"), pessoas_estimadas=27)
    assert valor_por_pessoa(c) == D("30.00")  # 29,63 → 30


def test_rateio_exato():
    c = Colaboracao(TipoColaboracao.RATEIO, meta=D("800"), pessoas_estimadas=40)
    assert valor_por_pessoa(c) == D("20.00")


@pytest.mark.parametrize(
    "colab",
    [
        Colaboracao(TipoColaboracao.FIXO),
        Colaboracao(TipoColaboracao.RATEIO, meta=D("800")),
        Colaboracao(TipoColaboracao.RATEIO, meta=D("800"), pessoas_estimadas=0),
    ],
)
def test_colaboracao_invalida(colab):
    with pytest.raises(ValueError):
        valor_por_pessoa(colab)


def test_soma_de_colaboracoes():
    colabs = [
        Colaboracao(TipoColaboracao.FIXO, valor_por_pessoa=D("30")),
        Colaboracao(TipoColaboracao.RATEIO, meta=D("200"), pessoas_estimadas=30),  # 6,67 → 7
    ]
    assert soma_por_pessoa(colabs) == D("37.00")


def test_valor_devido_com_acompanhantes():
    assert valor_devido(D("30.00"), 0) == D("30.00")
    assert valor_devido(D("30.00"), 2) == D("90.00")


@pytest.mark.parametrize(
    ("liquido", "cobrado"),
    [(D("30.00"), D("30.30")), (D("90.00"), D("90.90")), (D("100.00"), D("101.00"))],
)
def test_valor_com_taxa(liquido, cobrado):
    assert valor_com_taxa(liquido) == cobrado
    # Descontada a taxa (arredondada), o organizador recebe ao menos o líquido
    taxa = (cobrado * D("0.0099")).quantize(D("0.01"))
    assert cobrado - taxa >= liquido


def test_taxa_zero():
    assert valor_com_taxa(D("30.00"), D("0")) == D("30.00")
