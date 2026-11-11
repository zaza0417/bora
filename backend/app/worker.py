"""Worker: fila de mensagens + jobs agendados (docs/requisitos.md §6).

Rodar:  uv run python -m app.worker
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from app.config import get_settings
from app.db import get_sessionmaker
from app.domain.mensagens import TipoMensagem
from app.services.mensageria import enfileirar_mensagem, loop_envio

log = logging.getLogger("worker")


async def agendar_lembretes() -> None:
    """Diário 9h: LEMBRETE mensal, LEMBRETE_PRAZO (3 dias antes e no dia) e VESPERA."""
    sm = get_sessionmaker()
    async with sm() as s:
        # Lembrete mensal: 30 dias desde o convite/último lembrete, antes do prazo
        mensais = (
            (
                await s.execute(
                    text("""
                    select c.id from convidado c join evento e on e.id = c.evento_id
                     where e.status = 'ATIVO' and e.tem_contribuicao and not c.opt_out
                       and c.status in ('CONVIDADO', 'AGUARDANDO_PAGAMENTO')
                       and current_date < e.prazo_pagamento
                       and coalesce(c.ultimo_lembrete_em, c.convidado_em)
                           <= now() - interval '30 days'
                """)
                )
            )
            .scalars()
            .all()
        )
        for cid in mensais:
            await enfileirar_mensagem(s, cid, TipoMensagem.LEMBRETE)

        # Lembrete de prazo: 3 dias antes e no próprio dia
        de_prazo = (
            (
                await s.execute(
                    text("""
                    select c.id from convidado c join evento e on e.id = c.evento_id
                     where e.status = 'ATIVO' and e.tem_contribuicao and not c.opt_out
                       and c.status in ('CONVIDADO', 'AGUARDANDO_PAGAMENTO')
                       and e.prazo_pagamento - current_date in (3, 0)
                """)
                )
            )
            .scalars()
            .all()
        )
        for cid in de_prazo:
            await enfileirar_mensagem(s, cid, TipoMensagem.LEMBRETE_PRAZO)

        lembrados = list({*mensais, *de_prazo})
        if lembrados:
            await s.execute(
                text("update convidado set ultimo_lembrete_em = now() where id = any(:ids)"),
                {"ids": lembrados},
            )

        # Véspera para confirmados
        vespera = (
            (
                await s.execute(
                    text("""
                    select c.id from convidado c join evento e on e.id = c.evento_id
                     where e.status = 'ATIVO' and not c.opt_out and c.status = 'CONFIRMADO'
                       and (e.data_hora at time zone :fuso)::date = current_date + 1
                """),
                    {"fuso": get_settings().fuso},
                )
            )
            .scalars()
            .all()
        )
        for cid in vespera:
            await enfileirar_mensagem(s, cid, TipoMensagem.VESPERA)

        await s.commit()
    log.info(
        "lembretes: %d mensais, %d de prazo, %d véspera", len(mensais), len(de_prazo), len(vespera)
    )


async def expirar_cobrancas() -> None:
    async with get_sessionmaker()() as s:
        await s.execute(
            text(
                "update pagamento set status = 'EXPIRADO' "
                "where status = 'PENDENTE' and expira_em < now()"
            )
        )
        await s.commit()


async def encerrar_eventos() -> None:
    async with get_sessionmaker()() as s:
        await s.execute(
            text(
                "update evento set status = 'ENCERRADO' "
                "where status = 'ATIVO' and data_hora < now() - interval '1 day'"
            )
        )
        await s.commit()


async def renovar_tokens_mp() -> None:
    """Diário: renova tokens do MP que vencem em menos de 15 dias (RF-ORG-03)."""
    from app.api.integracoes import salvar_tokens_mp
    from app.integrations.mercadopago import ErroMercadoPago, renovar_token
    from app.security import descriptografar

    async with get_sessionmaker()() as s:
        vencendo = (
            await s.execute(
                text("""
                    select organizador_id, refresh_token_enc from integracao_mp
                     where status = 'ATIVA' and expira_em < now() + interval '15 days'
                """)
            )
        ).all()
        for org_id, refresh_enc in vencendo:
            try:
                dados = await renovar_token(descriptografar(refresh_enc))
                await salvar_tokens_mp(s, org_id, dados)
                log.info("token MP renovado para %s", org_id)
            except ErroMercadoPago as e:
                log.error("falha ao renovar token MP de %s: %s", org_id, e)
                await s.execute(
                    text("update integracao_mp set status = 'ERRO' where organizador_id = :o"),
                    {"o": org_id},
                )
            await s.commit()


async def checar_whatsapp() -> None:
    """A cada 10 min: sincroniza o status das instâncias (caso um webhook se perca)."""
    from app.api.integracoes import ESTADO_EVOLUTION
    from app.integrations.evolution import ErroEvolution, EvolutionClient

    evo = EvolutionClient.from_settings()
    async with get_sessionmaker()() as s:
        instancias = (await s.execute(text("select instancia from integracao_whatsapp"))).scalars()
        for inst in list(instancias):
            try:
                estado = ESTADO_EVOLUTION.get(await evo.estado(inst), "DESCONECTADO")
            except ErroEvolution:
                continue
            await s.execute(
                text(
                    "update integracao_whatsapp set status = cast(:st as status_whatsapp) "
                    "where instancia = :i and status::text <> :st"
                ),
                {"st": estado, "i": inst},
            )
        await s.commit()


async def reconciliar_pagamentos() -> None:
    """De hora em hora: consulta no MP as cobranças pendentes (caso um webhook se perca)."""
    from app.integrations.mercadopago import ErroMercadoPago
    from app.services.pagamentos import processar_order_mp

    async with get_sessionmaker()() as s:
        pendentes = (
            await s.execute(
                text("""
                    select p.mp_order_id, m.mp_user_id
                      from pagamento p
                      join convidado c on c.id = p.convidado_id
                      join evento e on e.id = c.evento_id
                      join integracao_mp m on m.organizador_id = e.organizador_id
                     where p.status = 'PENDENTE' and p.mp_order_id is not null
                       and p.criado_em < now() - interval '10 minutes'
                """)
            )
        ).all()
        for order_id, mp_user_id in pendentes:
            try:
                await processar_order_mp(s, order_id=order_id, mp_user_id=mp_user_id)
            except ErroMercadoPago as e:
                log.warning("reconciliação da order %s falhou: %s", order_id, e)
    if pendentes:
        log.info("reconciliação: %d cobrança(s) consultada(s)", len(pendentes))


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    fuso = ZoneInfo(get_settings().fuso)
    sched = AsyncIOScheduler(timezone=fuso)
    sched.add_job(agendar_lembretes, "cron", hour=9, minute=0, id="agendar_lembretes")
    sched.add_job(expirar_cobrancas, "interval", minutes=15, id="expirar_cobrancas")
    sched.add_job(encerrar_eventos, "cron", hour=3, minute=0, id="encerrar_eventos")
    sched.add_job(renovar_tokens_mp, "cron", hour=4, minute=0, id="renovar_tokens_mp")
    sched.add_job(checar_whatsapp, "interval", minutes=10, id="checar_whatsapp")
    sched.add_job(reconciliar_pagamentos, "interval", hours=1, id="reconciliar_pagamentos")
    sched.start()
    log.info("worker iniciado em %s", datetime.now(fuso).isoformat())
    await loop_envio(get_sessionmaker())


if __name__ == "__main__":
    asyncio.run(main())
