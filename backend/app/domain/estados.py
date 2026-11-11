"""Máquina de estados do convidado (RF-CNV-08, docs/requisitos.md §5)."""

from __future__ import annotations

from enum import StrEnum


class StatusConvidado(StrEnum):
    CONVIDADO = "CONVIDADO"
    AGUARDANDO_PAGAMENTO = "AGUARDANDO_PAGAMENTO"
    CONFIRMADO = "CONFIRMADO"
    RECUSOU = "RECUSOU"


class AcaoConvidado(StrEnum):
    ACEITAR = "ACEITAR"  # clicou "Vou"
    RECUSAR = "RECUSAR"  # clicou "Não vou"
    PAGAMENTO_APROVADO = "PAGAMENTO_APROVADO"
    BAIXA_MANUAL = "BAIXA_MANUAL"
    ESTORNO = "ESTORNO"


class TransicaoInvalida(Exception):
    def __init__(self, atual: StatusConvidado, acao: AcaoConvidado):
        super().__init__(f"Ação {acao} não permitida no status {atual}")
        self.atual = atual
        self.acao = acao


S = StatusConvidado
A = AcaoConvidado


def transicionar(
    atual: StatusConvidado, acao: AcaoConvidado, *, tem_contribuicao: bool
) -> StatusConvidado:
    """Retorna o novo status ou levanta TransicaoInvalida."""
    match acao:
        case A.ACEITAR if atual in (S.CONVIDADO, S.RECUSOU):
            return S.AGUARDANDO_PAGAMENTO if tem_contribuicao else S.CONFIRMADO
        case A.ACEITAR if atual in (S.AGUARDANDO_PAGAMENTO, S.CONFIRMADO):
            return atual  # idempotente
        case A.RECUSAR if atual in (S.CONVIDADO, S.AGUARDANDO_PAGAMENTO, S.RECUSOU):
            return S.RECUSOU
        case A.RECUSAR if atual is S.CONFIRMADO and not tem_contribuicao:
            return S.RECUSOU  # sem pagamento envolvido, pode desistir livremente
        case A.PAGAMENTO_APROVADO | A.BAIXA_MANUAL if tem_contribuicao:
            # Pagamento confirmado vale mesmo que a pessoa ainda não tenha clicado "Vou"
            # ou tenha recusado antes (pagou = vai).
            return S.CONFIRMADO
        case A.ESTORNO if atual is S.CONFIRMADO and tem_contribuicao:
            return S.AGUARDANDO_PAGAMENTO
    raise TransicaoInvalida(atual, acao)


def recebe_lembrete_pagamento(status: StatusConvidado) -> bool:
    return status in (S.CONVIDADO, S.AGUARDANDO_PAGAMENTO)
