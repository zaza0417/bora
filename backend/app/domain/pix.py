"""Gerador de PIX "copia e cola" (BR Code estático, padrão EMV/BCB).

Não depende de banco nem de gateway: basta a chave PIX do recebedor.
O valor vai embutido e o `txid` (identificador) aparece no comprovante
de muitos bancos, o que ajuda a casar o pagamento com o convidado.

Referência: Manual de Padrões para Iniciação do Pix (BCB), seção BR Code.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

GUI_PIX = "br.gov.bcb.pix"
MAX_NOME = 25
MAX_CIDADE = 15
MAX_TXID = 25


def _campo(id_: str, valor: str) -> str:
    if len(valor) > 99:
        raise ValueError(f"campo {id_} excede 99 caracteres")
    return f"{id_}{len(valor):02d}{valor}"


def _ascii(texto: str, limite: int) -> str:
    """Remove acentos e caracteres fora do permitido; corta no limite."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    limpo = re.sub(r"[^A-Za-z0-9 .\-]", "", sem_acento).strip()
    return limpo[:limite] or "RECEBEDOR"


def crc16_ccitt(dados: str) -> str:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), em hexa maiúsculo com 4 dígitos."""
    crc = 0xFFFF
    for byte in dados.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def gerar_copia_cola(
    chave: str,
    nome: str,
    cidade: str,
    valor: Decimal | None = None,
    txid: str | None = None,
) -> str:
    """Monta o payload do PIX copia e cola. Levanta ValueError se algo for inválido."""
    chave = chave.strip()
    if not chave:
        raise ValueError("chave PIX vazia")
    if valor is not None and valor <= 0:
        raise ValueError("valor deve ser positivo")

    txid_limpo = re.sub(r"[^A-Za-z0-9]", "", txid or "")[:MAX_TXID] or "***"

    conta = _campo("00", GUI_PIX) + _campo("01", chave)
    payload = (
        _campo("00", "01")  # Payload Format Indicator
        + _campo("26", conta)  # Merchant Account Information (PIX)
        + _campo("52", "0000")  # Merchant Category Code
        + _campo("53", "986")  # BRL
        + (_campo("54", f"{valor:.2f}") if valor is not None else "")
        + _campo("58", "BR")
        + _campo("59", _ascii(nome, MAX_NOME))
        + _campo("60", _ascii(cidade, MAX_CIDADE))
        + _campo("62", _campo("05", txid_limpo))  # Additional Data: txid
        + "6304"  # CRC (tamanho fixo 4) — calculado sobre tudo até aqui
    )
    return payload + crc16_ccitt(payload)


def txid_do_convidado(convidado_id: str) -> str:
    """Identificador curto e legível para aparecer no comprovante: BORA + 8 hex."""
    return "BORA" + convidado_id.replace("-", "")[:8].upper()
