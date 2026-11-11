from datetime import date
from decimal import Decimal as D

from app.domain.comprovante import (
    analisar,
    extrair_datas,
    extrair_e2e,
    extrair_valores,
    nome_aparece,
)

# Textos no estilo do que o OCR devolve de comprovantes reais (dados fictícios)
NUBANK = """
Comprovante de transferência
10 NOV 2026 - 14:32:07
Valor
R$ 30,00
Tipo de transferência
Pix
Destino
Nome Isac Carmo Alves
CPF •••.123.456-••
Instituição MERCADO PAGO IP LTDA.
Origem
Nome Ana Paula Souza
Instituição NU PAGAMENTOS - IP
ID da transação:
E18236120202611101732s0123abcDEF
"""

ITAU = """
Pix enviado
valor: R$ 1.250,50
data da transferência: 10/11/2026 às 09:15
para: ISAC CARMO
pagador: JOSE DA SILVA
autenticação E60701190202611100915ABCDE123456
"""

HOJE = date(2026, 11, 10)
DESDE = date(2026, 11, 1)


# --- extração ---------------------------------------------------------------------
def test_valores():
    assert extrair_valores(NUBANK) == [D("30.00")]
    assert extrair_valores(ITAU) == [D("1250.50")]
    assert extrair_valores("Total 45,90 pago") == [D("45.90")]
    assert extrair_valores("R$30,30") == [D("30.30")]


def test_datas_numericas_e_por_extenso():
    assert extrair_datas(ITAU) == [date(2026, 11, 10)]
    assert extrair_datas(NUBANK) == [date(2026, 11, 10)]
    assert extrair_datas("10 de novembro de 2026") == [date(2026, 11, 10)]
    assert extrair_datas("10/11/26") == [date(2026, 11, 10)]
    assert extrair_datas("31/02/2026") == []  # data impossível


def test_e2e():
    assert extrair_e2e(NUBANK) == "E18236120202611101732s0123abcDEF"
    assert extrair_e2e("sem id") is None


def test_nomes():
    assert nome_aparece("Ana Paula Souza", NUBANK)
    assert nome_aparece("Isac Carmo", NUBANK)
    assert nome_aparece("Isac", ITAU)
    assert nome_aparece("Ísac Cármo", "PARA: ISAC CARMO")  # acentos
    assert nome_aparece("Isac Carmo Alves", "Isac C Alves")  # abreviado
    assert not nome_aparece("Bruno Lima", NUBANK)
    assert not nome_aparece("Ana Lima", "Mariana Lima")  # 'ana' dentro de 'mariana' não conta


# --- conferência -------------------------------------------------------------------
def _analisar(texto, valor="30.00", convidado="Ana Paula Souza", recebedor="Isac Carmo", **kw):
    return analisar(
        texto,
        valor_esperado=D(valor),
        nome_convidado=convidado,
        nome_recebedor=recebedor,
        desde=kw.pop("desde", DESDE),
        hoje=kw.pop("hoje", HOJE),
        **kw,
    )


def test_tudo_confere():
    a = _analisar(NUBANK)
    assert a.valor_confere and a.data_confere and a.recebedor_confere and a.convidado_confere
    assert not a.repetido and a.tudo_confere


def test_outra_pessoa_pagou_ainda_confere():
    a = _analisar(NUBANK, convidado="Bruno Lima")
    assert not a.convidado_confere and a.tudo_confere


def test_valor_diferente():
    a = _analisar(NUBANK, valor="60.00")
    assert not a.valor_confere and not a.tudo_confere


def test_comprovante_antigo():
    a = _analisar(NUBANK, desde=date(2026, 11, 11), hoje=date(2026, 11, 12))
    assert not a.data_confere and not a.tudo_confere


def test_recebedor_errado():
    a = _analisar(NUBANK, recebedor="Carlos Pereira")
    assert a.recebedor_confere is False and not a.tudo_confere


def test_sem_nome_de_recebedor_cadastrado_nao_bloqueia():
    a = _analisar(NUBANK, recebedor=None)
    assert a.recebedor_confere is None and a.tudo_confere


def test_comprovante_repetido():
    a = _analisar(NUBANK, e2e_ja_usados={"E18236120202611101732s0123abcDEF"})
    assert a.repetido and not a.tudo_confere


def test_texto_ilegivel():
    a = _analisar("@#")
    assert not a.texto_legivel and not a.tudo_confere
    assert _analisar(None).texto_legivel is False


def test_json():
    d = _analisar(NUBANK).para_json()
    assert d["tudo_confere"] is True and d["valores_encontrados"] == ["30.00"]
