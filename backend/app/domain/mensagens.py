"""Templates de mensagens do WhatsApp (RF-MSG, docs/requisitos.md §8).

Cada tipo tem algumas variações para reduzir o risco de bloqueio do número (RF-MSG-07).
Variáveis disponíveis: {nome} {evento} {data} {local} {valor} {prazo} {link}
"""

from __future__ import annotations

import random
from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum


class TipoMensagem(StrEnum):
    CONVITE = "CONVITE"
    LEMBRETE = "LEMBRETE"
    LEMBRETE_PRAZO = "LEMBRETE_PRAZO"
    CONFIRMACAO = "CONFIRMACAO"
    VESPERA = "VESPERA"
    ALTERACAO = "ALTERACAO"
    CANCELAMENTO = "CANCELAMENTO"
    COMPROVANTE_RECEBIDO = "COMPROVANTE_RECEBIDO"


TEMPLATES_PADRAO: dict[TipoMensagem, list[str]] = {
    TipoMensagem.CONVITE: [
        "Oi, {nome}! 🎉 Você está convidado(a) para *{evento}*, dia {data} em {local}.\n"
        "Confirma sua presença por aqui: {link}",
        "{nome}, tudo bem? Vai rolar *{evento}* no dia {data} ({local}) e você está na lista! 🥳\n"
        "Confirme aqui: {link}",
    ],
    TipoMensagem.LEMBRETE: [
        "Oi, {nome}! Passando para lembrar do *{evento}* ({data}). "
        "Sua contribuição de {valor} ainda está pendente — dá para pagar até {prazo}: {link}",
        "{nome}, lembrete rapidinho: a contribuição de {valor} para *{evento}* "
        "pode ser paga até {prazo}. É só acessar: {link}",
    ],
    TipoMensagem.LEMBRETE_PRAZO: [
        "Oi, {nome}! O prazo para a contribuição de {valor} do *{evento}* é {prazo}. "
        "Garanta sua presença: {link}",
        "{nome}, o prazo da contribuição do *{evento}* está chegando ({prazo}). "
        "Valor: {valor}. Link: {link}",
    ],
    TipoMensagem.CONFIRMACAO: [
        "Presença confirmada, {nome}! ✅ Te esperamos no *{evento}*, dia {data}. Detalhes: {link}",
        "Tudo certo, {nome}! ✅ Sua presença no *{evento}* ({data}) está confirmada. {link}",
    ],
    TipoMensagem.VESPERA: [
        "É amanhã! 🎈 *{evento}*, {data} em {local}. Até lá, {nome}!",
        "{nome}, amanhã tem *{evento}*! 🎉 {data} — {local}. Detalhes: {link}",
    ],
    TipoMensagem.ALTERACAO: [
        "{nome}, atenção: o *{evento}* teve alteração. Agora é {data} em {local}. Detalhes: {link}",
    ],
    TipoMensagem.COMPROVANTE_RECEBIDO: [
        "Recebemos seu comprovante, {nome}! ✅ Assim que o organizador conferir, "
        "sua presença no *{evento}* fica confirmada e você recebe um aviso aqui.",
    ],
    TipoMensagem.CANCELAMENTO: [
        "Oi, {nome}. Infelizmente o *{evento}* ({data}) foi cancelado. "
        "Quem já contribuiu será contatado pelo organizador.",
    ],
}


class _SafeDict(dict):
    def __missing__(self, chave: str) -> str:
        return "{" + chave + "}"


def formatar_moeda(valor: Decimal) -> str:
    inteiro, _, centavos = f"{valor:.2f}".partition(".")
    inteiro = f"{int(inteiro):,}".replace(",", ".")
    return f"R$ {inteiro},{centavos}"


def formatar_data(valor: date | datetime) -> str:
    if isinstance(valor, datetime):
        if valor.time() == time(0, 0):
            return valor.strftime("%d/%m/%Y")
        return valor.strftime("%d/%m/%Y às %Hh%M").replace("h00", "h")
    return valor.strftime("%d/%m/%Y")


def renderizar(
    tipo: TipoMensagem,
    variaveis: dict[str, object],
    templates: dict[TipoMensagem, list[str]] | None = None,
    rng: random.Random | None = None,
) -> str:
    opcoes = (templates or TEMPLATES_PADRAO)[tipo]
    escolhido = (rng or random).choice(opcoes)
    vars_fmt: dict[str, str] = {}
    for chave, valor in variaveis.items():
        if isinstance(valor, Decimal):
            vars_fmt[chave] = formatar_moeda(valor)
        elif isinstance(valor, date | datetime):
            vars_fmt[chave] = formatar_data(valor)
        else:
            vars_fmt[chave] = "" if valor is None else str(valor)
    return escolhido.format_map(_SafeDict(vars_fmt))
