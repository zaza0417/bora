from datetime import date
from decimal import Decimal as D

from app.domain.comprovante import Destino, analisar, destino

HOJE = date(2026, 11, 10)
DESDE = date(2026, 11, 1)

COMPROVANTE_30 = """
Comprovante de transferência
10 NOV 2026 - 14:32:07
Valor R$ 30,00
Tipo de transferência Pix
Destino Isac Carmo Alves
Origem Ana Paula Souza
"""

COMPROVANTE_50 = COMPROVANTE_30.replace("30,00", "50,00")

# OCR de uma foto da festa / print de conversa: tem texto, mas não é comprovante
PRINT_CONVERSA = """
Ana: gente o churras vai ser que horas??
Bruno: 19h, leva a caixa de som
Ana: fechou! vou levar o violão também kkkk
"""

CARDAPIO = """
Cardápio do Bar do Zé
Picanha na chapa R$ 89,90
Porção de fritas R$ 32,00
"""


def _analise(texto, *, usados=None):
    return analisar(
        texto,
        valor_esperado=D("30.00"),
        nome_convidado="Ana Souza",
        nome_recebedor="Isac Alves",
        desde=DESDE,
        hoje=HOJE,
        e2e_ja_usados=usados,
    )


def test_comprovante_certo_e_avisado():
    assert destino(_analise(COMPROVANTE_30), ja_tem_o_certo=False) is Destino.RECEBIDO


def test_print_de_conversa_e_ignorado():
    a = _analise(PRINT_CONVERSA)
    assert not a.parece_comprovante
    assert destino(a, ja_tem_o_certo=False) is Destino.IGNORAR


def test_foto_com_valor_mas_sem_cara_de_comprovante_e_ignorada():
    # cardápio tem R$ mas não é transferência
    assert destino(_analise(CARDAPIO), ja_tem_o_certo=False) is Destino.IGNORAR


def test_foto_sem_texto_e_ignorada():
    assert destino(_analise("   "), ja_tem_o_certo=False) is Destino.IGNORAR
    assert destino(_analise(None), ja_tem_o_certo=False) is Destino.IGNORAR


def test_comprovante_de_outro_valor_vai_para_conferir_sem_avisar():
    assert destino(_analise(COMPROVANTE_50), ja_tem_o_certo=False) is Destino.CONFERIR


def test_segundo_comprovante_nao_repete_o_aviso():
    assert destino(_analise(COMPROVANTE_30), ja_tem_o_certo=True) is Destino.IGNORAR


def test_comprovante_repetido_vai_para_conferir():
    texto = COMPROVANTE_30 + "\nID da transação:\nE18236120202611101732s0123abcDEF"
    a = _analise(texto, usados={"E18236120202611101732s0123abcDEF"})
    assert a.repetido
    assert destino(a, ja_tem_o_certo=False) is Destino.CONFERIR


def test_sem_midia_vai_para_conferir_uma_vez():
    assert destino(None, ja_tem_o_certo=False) is Destino.CONFERIR
    assert destino(None, ja_tem_o_certo=True) is Destino.IGNORAR


def test_ilegivel_nao_conta_como_tudo_confere():
    assert not _analise(PRINT_CONVERSA).tudo_confere
