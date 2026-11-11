"""Normalização de telefone para E.164 (RF-CNV-03)."""

from __future__ import annotations

import phonenumbers


class TelefoneInvalido(ValueError):
    pass


def normalizar_telefone(bruto: str, regiao_padrao: str = "BR") -> str:
    """'(11) 98765-4321' → '+5511987654321'. Levanta TelefoneInvalido se não for válido."""
    try:
        numero = phonenumbers.parse(bruto, regiao_padrao)
    except phonenumbers.NumberParseException as e:
        raise TelefoneInvalido(f"Telefone inválido: {bruto!r}") from e
    if not phonenumbers.is_valid_number(numero):
        numero = _completar_nono_digito(numero)
    if numero is None or not phonenumbers.is_valid_number(numero):
        raise TelefoneInvalido(f"Telefone inválido: {bruto!r}")
    return phonenumbers.format_number(numero, phonenumbers.PhoneNumberFormat.E164)


def _completar_nono_digito(numero: phonenumbers.PhoneNumber) -> phonenumbers.PhoneNumber | None:
    """Celular brasileiro no formato antigo (8 dígitos, ex.: 61 9123-4567) → acrescenta o 9.

    Contas antigas de WhatsApp e pessoas que digitam sem o 9 geram esse formato.
    """
    nacional = str(numero.national_number)
    if numero.country_code != 55 or len(nacional) != 10 or nacional[2] not in "6789":
        return None
    novo = phonenumbers.PhoneNumber(
        country_code=55, national_number=int(nacional[:2] + "9" + nacional[2:])
    )
    return novo if phonenumbers.is_valid_number(novo) else None


def para_whatsapp(e164: str) -> str:
    """Formato aceito pela Evolution API: só dígitos, com DDI ('5511987654321')."""
    return e164.lstrip("+")
