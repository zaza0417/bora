"""Texto visível de um comprovante: PDF (texto direto) ou imagem (OCR com Tesseract).

Tesseract é um programa à parte (não é IA generativa). Instalação:
  * Docker/Linux: apt-get install tesseract-ocr tesseract-ocr-por
  * Windows: instalador UB Mannheim (com o idioma "Portuguese")
Sem Tesseract, imagens voltam None e o comprovante fica para conferência manual.
"""

from __future__ import annotations

import io
import logging
import shutil
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

CAMINHOS_WINDOWS = [
    Path.home() / "AppData/Local/Programs/Tesseract-OCR/tesseract.exe",
    Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
]


@lru_cache
def _tesseract() -> str | None:
    achado = shutil.which("tesseract")
    if achado:
        return achado
    for p in CAMINHOS_WINDOWS:
        if p.exists():
            return str(p)
    return None


def ocr_disponivel() -> bool:
    return _tesseract() is not None


def extrair_texto(conteudo: bytes, mimetype: str) -> str | None:
    """Síncrono (CPU): chame com asyncio.to_thread."""
    tipo = (mimetype or "").split(";")[0].lower()
    try:
        if tipo == "application/pdf":
            return _texto_pdf(conteudo)
        if tipo.startswith("image/"):
            return _texto_imagem(conteudo)
    except Exception as e:  # noqa: BLE001 — arquivo corrompido não pode derrubar o webhook
        log.warning("falha ao extrair texto do comprovante (%s): %s", tipo, e)
    return None


def _texto_pdf(conteudo: bytes) -> str | None:
    from pypdf import PdfReader

    leitor = PdfReader(io.BytesIO(conteudo))
    texto = "\n".join((pg.extract_text() or "") for pg in leitor.pages[:3])
    return texto.strip() or None  # PDF escaneado (só imagem) não tem texto


def _texto_imagem(conteudo: bytes) -> str | None:
    binario = _tesseract()
    if not binario:
        log.info("Tesseract não instalado — comprovante segue para conferência manual")
        return None
    import pytesseract
    from PIL import Image, ImageOps

    pytesseract.pytesseract.tesseract_cmd = binario
    img = Image.open(io.BytesIO(conteudo))
    img = ImageOps.exif_transpose(img).convert("L")  # gira foto de celular + tons de cinza
    if img.width < 1000:  # prints pequenos: ampliar melhora muito o OCR
        fator = 1000 / img.width
        img = img.resize((1000, int(img.height * fator)))
    texto = pytesseract.image_to_string(img, lang="por", config="--psm 6")
    return texto.strip() or None
