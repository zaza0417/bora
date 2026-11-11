"""Como cada organizador recebe: Mercado Pago (automático) ou PIX manual (chave própria)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.valores import valor_com_taxa

Modo = Literal["MERCADO_PAGO", "PIX_MANUAL", "NENHUM"]


@dataclass(frozen=True)
class ModoPagamento:
    modo: Modo
    pix_chave: str | None = None
    pix_nome: str | None = None
    pix_cidade: str | None = None
    whatsapp_numero: str | None = None  # só dígitos, com DDI — para o link wa.me

    @property
    def cobra_taxa(self) -> bool:
        return self.modo == "MERCADO_PAGO"

    def valor_cobrado(self, valor_devido: Decimal, taxa: Decimal) -> Decimal:
        return valor_com_taxa(valor_devido, taxa) if self.cobra_taxa else valor_devido


async def modo_pagamento(sessao: AsyncSession, organizador_id: UUID) -> ModoPagamento:
    row = (
        (
            await sessao.execute(
                text("""
                    select o.pix_chave, o.pix_nome, o.pix_cidade, o.telefone,
                           exists(select 1 from integracao_mp m
                                   where m.organizador_id = o.id and m.status = 'ATIVA') as mp,
                           (select w.numero from integracao_whatsapp w
                             where w.organizador_id = o.id and w.status = 'CONECTADO') as wa
                      from organizador o where o.id = :id
                """),
                {"id": organizador_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return ModoPagamento("NENHUM")
    numero = row["wa"] or (row["telefone"] or "").lstrip("+") or None
    if row["mp"]:
        return ModoPagamento("MERCADO_PAGO", whatsapp_numero=numero)
    if row["pix_chave"]:
        return ModoPagamento(
            "PIX_MANUAL", row["pix_chave"], row["pix_nome"], row["pix_cidade"], numero
        )
    return ModoPagamento("NENHUM", whatsapp_numero=numero)


def link_whatsapp_comprovante(numero: str, nome_convidado: str, evento: str, valor: Decimal) -> str:
    """Abre a conversa com o organizador já com o texto pronto; o convidado anexa a imagem."""
    texto = (
        f"Oi! Segue o comprovante da minha contribuição para *{evento}* 🎉\n"
        f"{nome_convidado} — R$ {valor:.2f}".replace(".", ",")
    )
    return f"https://wa.me/{numero}?text={quote(texto)}"
