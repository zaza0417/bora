"""Cartaz 1200×630 do convite, no tema do evento — a imagem da prévia do link (WhatsApp).

Função pura (Pillow): recebe os dados e as fontes, devolve o PNG. Mostra só o evento
(nome, data, local), nunca o convidado: a imagem pode ser repassada.
Cores iguais às de frontend/.../convite.scss e das miniaturas do formulário.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

LARGURA, ALTURA = 1200, 630
MARGEM = 72

DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]  # fmt: skip


@dataclass(frozen=True)
class Visual:
    fundo: str
    tinta: str
    destaque: str  # cor da data
    fonte: str  # chave em Fontes: "titulo_pesado", "titulo_leve" ou "titulo_serifa"
    centro: bool


VISUAIS = {
    "FESTA": Visual("#ffd23f", "#1d1d1f", "#5c4a12", "titulo_pesado", False),
    "NOITE": Visual("#0e0e10", "#f5f1e6", "#c9a95c", "titulo_leve", False),
    "CASAMENTO": Visual("#f6f1e9", "#3b3329", "#8a6a3f", "titulo_serifa", True),
    "INFANTIL": Visual("#2f7bf0", "#ffffff", "#ffffff", "titulo_pesado", False),
}


@dataclass(frozen=True)
class Fontes:
    """Bytes de TTF. None → fonte embutida da Pillow (testes, ou Google Fonts fora do ar)."""

    titulo_pesado: bytes | None = None  # Bricolage Grotesque 800
    titulo_leve: bytes | None = None  # Bricolage Grotesque 500
    titulo_serifa: bytes | None = None  # Fraunces 400
    texto: bytes | None = None  # Geist 500


def quando(data_hora: datetime, fuso: str = "America/Sao_Paulo") -> str:
    """'Sábado, 16 de janeiro, 15h' (ou '15h30')."""
    d = data_hora.astimezone(ZoneInfo(fuso))
    hora = f"{d.hour}h" + (f"{d.minute:02d}" if d.minute else "")
    return f"{DIAS[d.weekday()]}, {d.day} de {MESES[d.month - 1]}, {hora}"


def _fonte(dados: bytes | None, tamanho: int) -> ImageFont.FreeTypeFont:
    if dados:
        return ImageFont.truetype(io.BytesIO(dados), tamanho)
    return ImageFont.load_default(tamanho)


def _quebrar(texto: str, fonte: ImageFont.FreeTypeFont, largura: int) -> list[str]:
    linhas: list[str] = []
    atual = ""
    for palavra in texto.split():
        tentativa = f"{atual} {palavra}".strip()
        if fonte.getlength(tentativa) <= largura or not atual:
            atual = tentativa
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _titulo(
    nome: str, dados: bytes | None, largura: int, max_linhas: int, altura: int, entrelinha: float
):
    """Maior tamanho em que o nome cabe na largura, em até `max_linhas` e na `altura`."""
    for tamanho in (132, 116, 102, 90, 80, 70, 62, 56):
        fonte = _fonte(dados, tamanho)
        linhas = _quebrar(nome, fonte, largura)
        cabe_largura = all(fonte.getlength(lin) <= largura for lin in linhas)
        cabe_altura = len(linhas) * tamanho * entrelinha <= altura
        if len(linhas) <= max_linhas and cabe_largura and cabe_altura:
            return fonte, linhas, tamanho
    fonte = _fonte(dados, 56)
    linhas = _quebrar(nome, fonte, largura)[:max_linhas]
    linhas[-1] = linhas[-1][: max(1, len(linhas[-1]) - 1)].rstrip() + "…"
    return fonte, linhas, 56


def desenhar_cartaz(
    *, nome: str, data_hora: datetime, local: str | None, tema: str, fontes: Fontes
) -> bytes:
    v = VISUAIS.get(tema, VISUAIS["FESTA"])
    img = Image.new("RGB", (LARGURA, ALTURA), v.fundo)
    d = ImageDraw.Draw(img)
    largura_util = LARGURA - 2 * MARGEM

    texto = _fonte(fontes.texto, 34)
    pequeno = _fonte(fontes.texto, 30)
    fator = 1.04 if v.centro else 0.94
    # Espaço do nome = altura útil menos data, local, bolinhas e a faixa da marca no topo
    reservado = 64 + (82 if local else 0) + (84 if tema == "INFANTIL" else 0) + 56
    if v.centro:
        reservado = 30 + 56 + (48 if local else 0) + 56
    fonte_titulo, linhas, tamanho = _titulo(
        nome,
        getattr(fontes, v.fonte),
        largura_util,
        2 if v.centro else 3,
        ALTURA - 2 * MARGEM - reservado,
        fator,
    )
    entrelinha = int(tamanho * fator)
    data = quando(data_hora)

    # marca discreta no canto
    d.text((LARGURA - MARGEM, 52), "bora", font=pequeno, fill=v.tinta, anchor="ra")

    if v.centro:
        # Casamento: tudo centralizado — nome, um fio, data e local
        altura = len(linhas) * entrelinha + 30 + 2 + 26 + 40 + (46 if local else 0)
        y = (ALTURA - altura) // 2 + int(tamanho * 0.8)
        for lin in linhas:
            d.text((LARGURA // 2, y), lin, font=fonte_titulo, fill=v.tinta, anchor="ms")
            y += entrelinha
        y += 30 - entrelinha + int(tamanho * 0.25)
        d.line([(LARGURA // 2 - 32, y), (LARGURA // 2 + 32, y)], fill=v.destaque, width=2)
        y += 56
        d.text((LARGURA // 2, y), data, font=texto, fill=v.destaque, anchor="ms")
        if local:
            d.text((LARGURA // 2, y + 48), local, font=texto, fill=v.tinta, anchor="ms")
    else:
        # Festa, Noite e Infantil: alinhado embaixo à esquerda, como o cartaz do convite
        y = ALTURA - MARGEM
        if local:
            d.text((MARGEM, y), local, font=texto, fill=v.tinta, anchor="ls")
            y -= 52 + int(tamanho * 0.22)  # espaço para as letras com "perna" (g, p, j)
        for lin in reversed(linhas):
            d.text((MARGEM, y), lin, font=fonte_titulo, fill=v.tinta, anchor="ls")
            y -= entrelinha
        y -= int(tamanho * 0.12)
        d.text((MARGEM, y), data, font=texto, fill=v.destaque, anchor="ls")
        if tema == "INFANTIL":
            y -= 84
            for i, cor in enumerate(("#ff5d73", "#ffd23f", "#2ec4a0")):
                x = MARGEM + i * 48
                d.ellipse([(x, y), (x + 34, y + 34)], fill=cor)

    saida = io.BytesIO()
    img.save(saida, "PNG", optimize=True)
    return saida.getvalue()
