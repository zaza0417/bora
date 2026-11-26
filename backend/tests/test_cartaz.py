import io
from datetime import UTC, datetime

import pytest
from PIL import Image

from app.domain.cartaz import VISUAIS, Fontes, desenhar_cartaz, quando


def _png(**kw):
    base = {
        "nome": "Aniversário da Bia",
        "data_hora": datetime(2027, 1, 16, 18, 0, tzinfo=UTC),
        "local": "Chácara Recanto",
        "tema": "FESTA",
        "fontes": Fontes(),
    }
    return Image.open(io.BytesIO(desenhar_cartaz(**{**base, **kw})))


def test_quando_no_horario_de_brasilia():
    assert quando(datetime(2027, 1, 16, 18, 0, tzinfo=UTC)) == "Sábado, 16 de janeiro, 15h"
    assert quando(datetime(2027, 3, 14, 19, 30, tzinfo=UTC)) == "Domingo, 14 de março, 16h30"


@pytest.mark.parametrize("tema", list(VISUAIS))
def test_cada_tema_tem_o_tamanho_e_a_cor_de_fundo(tema):
    img = _png(tema=tema)
    assert img.size == (1200, 630)
    fundo = VISUAIS[tema].fundo.lstrip("#")
    assert img.convert("RGB").getpixel((5, 5)) == tuple(
        int(fundo[i : i + 2], 16) for i in (0, 2, 4)
    )


def test_tema_desconhecido_usa_festa():
    assert _png(tema="OUTRO").convert("RGB").getpixel((5, 5)) == (0xFF, 0xD2, 0x3F)


@pytest.mark.parametrize(
    "nome",
    [
        "Bia",
        "Churrasco de fim de ano da firma com as famílias e os amigos de sempre",
        "Supercalifragilistico" * 3,
    ],
)
def test_nomes_curtos_e_longos_cabem(nome):
    for tema in VISUAIS:
        img = _png(nome=nome, tema=tema, local=None)
        assert img.size == (1200, 630)
