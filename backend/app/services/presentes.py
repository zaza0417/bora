"""Consultas da lista de presentes usadas pela página do convidado e pelo painel."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class PixOrganizador:
    chave: str
    nome: str | None
    cidade: str | None


async def pix_do_organizador(sessao: AsyncSession, organizador_id: UUID) -> PixOrganizador | None:
    """Chave PIX própria do organizador (presente em dinheiro vai direto para ela)."""
    row = (
        (
            await sessao.execute(
                text("select pix_chave, pix_nome, pix_cidade from organizador where id = :id"),
                {"id": organizador_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None or not (row["pix_chave"] or "").strip():
        return None
    return PixOrganizador(row["pix_chave"].strip(), row["pix_nome"], row["pix_cidade"])


_SQL_PRESENTES_CONVIDADO = text("""
    select p.id, p.nome, p.descricao, p.link_loja, p.imagem_url, p.modo::text as modo,
           p.valor_referencia,
           p.reservado_por is not null as reservado,
           p.reservado_por is not distinct from :convidado_id as reservado_por_mim,
           coalesce(sum(pg.valor_liquido) filter (where pg.status = 'APROVADO'), 0) as arrecadado,
           coalesce(sum(pg.valor_liquido) filter (where pg.status = 'PENDENTE'
                                                    and pg.convidado_id = :convidado_id), 0)
             as meu_valor_a_conferir,
           coalesce(sum(pg.valor_liquido) filter (where pg.status = 'APROVADO'
                                                    and pg.convidado_id = :convidado_id), 0)
             as meu_valor_confirmado
      from presente p
      left join pagamento pg on pg.presente_id = p.id and pg.tipo = 'PRESENTE'
     where p.evento_id = :evento_id
     group by p.id
     order by p.ordem, p.nome
""")


async def presentes_do_convidado(
    sessao: AsyncSession, evento_id: UUID, convidado_id: UUID
) -> list[dict]:
    res = await sessao.execute(
        _SQL_PRESENTES_CONVIDADO, {"evento_id": evento_id, "convidado_id": convidado_id}
    )
    return [dict(r) for r in res.mappings()]


async def presentes_do_evento(sessao: AsyncSession, evento_id: UUID) -> list[dict]:
    """Visão do organizador: quem reservou, quanto entrou e o que falta conferir."""
    presentes = (
        (
            await sessao.execute(
                text("""
                select p.id, p.nome, p.modo::text as modo, p.valor_referencia,
                       c.nome as reservado_por_nome, p.reservado_em,
                       coalesce((select sum(pg.valor_liquido) from pagamento pg
                                  where pg.presente_id = p.id and pg.status = 'APROVADO'), 0)
                         as arrecadado
                  from presente p
                  left join convidado c on c.id = p.reservado_por
                 where p.evento_id = :ev
                 order by p.ordem, p.nome
            """),
                {"ev": evento_id},
            )
        )
        .mappings()
        .all()
    )
    pagamentos = (
        (
            await sessao.execute(
                text("""
                select pg.id, pg.presente_id, pg.valor_liquido as valor, pg.status::text as status,
                       pg.criado_em, pg.pago_em, c.nome as convidado_nome
                  from pagamento pg
                  join convidado c on c.id = pg.convidado_id
                  join presente p on p.id = pg.presente_id
                 where p.evento_id = :ev and pg.tipo = 'PRESENTE'
                   and pg.status in ('PENDENTE', 'APROVADO')
                 order by pg.criado_em
            """),
                {"ev": evento_id},
            )
        )
        .mappings()
        .all()
    )
    por_presente: dict[UUID, list[dict]] = {}
    for pg in pagamentos:
        por_presente.setdefault(pg["presente_id"], []).append(dict(pg))
    return [{**dict(p), "pagamentos": por_presente.get(p["id"], [])} for p in presentes]
