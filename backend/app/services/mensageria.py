"""Fila de mensagens do WhatsApp (tabela `mensagem`) — RF-MSG."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.domain.mensagens import TipoMensagem, renderizar
from app.domain.telefone import para_whatsapp
from app.integrations.evolution import EvolutionClient
from app.services.cobranca import modo_pagamento

log = logging.getLogger(__name__)


async def enfileirar_mensagem(sessao: AsyncSession, convidado_id: UUID, tipo: TipoMensagem) -> None:
    """Renderiza o texto e coloca na fila. Não faz commit (fica na transação do chamador)."""
    c = (
        (
            await sessao.execute(
                text("""
                select c.nome, c.token, c.valor_devido, c.opt_out,
                       e.nome as evento, e.data_hora, e.local_nome, e.prazo_pagamento, e.taxa_mp,
                       e.convite_imagem_url, e.organizador_id
                  from convidado c join evento e on e.id = c.evento_id
                 where c.id = :id
            """),
                {"id": convidado_id},
            )
        )
        .mappings()
        .first()
    )
    if c is None or c["opt_out"]:
        return

    s = get_settings()
    fuso = ZoneInfo(s.fuso)
    valor = None
    if c["valor_devido"] > 0:
        modo = await modo_pagamento(sessao, c["organizador_id"])
        valor = modo.valor_cobrado(c["valor_devido"], c["taxa_mp"])
    conteudo = renderizar(
        tipo,
        {
            "nome": c["nome"].split()[0],
            "evento": c["evento"],
            "data": c["data_hora"].astimezone(fuso),
            "local": c["local_nome"],
            "valor": valor,
            "prazo": c["prazo_pagamento"],
            "link": f"{s.url_publica_front.rstrip('/')}/c/{c['token']}",
        },
    )
    # A arte do convite vai junto só na mensagem de CONVITE (texto vira legenda da imagem)
    midia_url = c["convite_imagem_url"] if tipo is TipoMensagem.CONVITE else None
    await sessao.execute(
        text("""
            insert into mensagem (convidado_id, tipo, conteudo, midia_url)
            values (:id, :tipo, :conteudo, :midia)
        """),
        {"id": convidado_id, "tipo": tipo.value, "conteudo": conteudo, "midia": midia_url},
    )


def dentro_da_janela(agora: datetime) -> bool:
    s = get_settings()
    hora = agora.astimezone(ZoneInfo(s.fuso)).hour
    return s.janela_envio_inicio <= hora < s.janela_envio_fim


_SQL_PROXIMA = text("""
    select m.id, m.conteudo, m.midia_url, m.tentativas, cv.telefone_e164, w.instancia
      from mensagem m
      join convidado cv on cv.id = m.convidado_id
      join evento e on e.id = cv.evento_id
      join integracao_whatsapp w on w.organizador_id = e.organizador_id and w.status = 'CONECTADO'
     where m.status = 'PENDENTE' and m.agendada_para <= now()
     order by m.agendada_para
     limit 1
     for update of m skip locked
""")


async def enviar_proxima(sessionmaker: async_sessionmaker[AsyncSession]) -> bool:
    """Envia uma mensagem da fila. Retorna True se enviou/tentou, False se a fila está vazia."""
    s = get_settings()
    evo = EvolutionClient.from_settings()
    async with sessionmaker() as sessao:
        m = (await sessao.execute(_SQL_PROXIMA)).mappings().first()
        if m is None:
            return False
        try:
            numero = para_whatsapp(m["telefone_e164"])
            if m["midia_url"]:
                id_ext = await evo.enviar_imagem(
                    m["instancia"], numero, m["midia_url"], legenda=m["conteudo"]
                )
            else:
                id_ext = await evo.enviar_texto(m["instancia"], numero, m["conteudo"])
        except Exception as e:  # noqa: BLE001 — qualquer falha conta como tentativa
            tentativas = m["tentativas"] + 1
            falhou = tentativas >= s.max_tentativas_envio
            await sessao.execute(
                text("""
                    update mensagem
                       set tentativas = :t, erro = :erro,
                           status = case when :falhou then 'FALHA'::status_mensagem
                                         else status end,
                           agendada_para = now() + make_interval(mins => 5 * :t)
                     where id = :id
                """),
                {"t": tentativas, "erro": str(e)[:1000], "falhou": falhou, "id": m["id"]},
            )
            log.warning("Falha ao enviar mensagem %s: %s", m["id"], e)
        else:
            await sessao.execute(
                text("""
                    update mensagem set status = 'ENVIADA', enviada_em = now(), id_externo = :ext
                     where id = :id
                """),
                {"ext": id_ext, "id": m["id"]},
            )
        await sessao.commit()
        return True


async def loop_envio(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    """Worker contínuo: respeita janela de horário e intervalo aleatório (RF-MSG-06)."""
    s = get_settings()
    while True:
        try:
            if dentro_da_janela(datetime.now(ZoneInfo(s.fuso))) and await enviar_proxima(
                sessionmaker
            ):
                await asyncio.sleep(
                    random.uniform(s.intervalo_envio_min_s, s.intervalo_envio_max_s)
                )
                continue
        except Exception:  # noqa: BLE001
            log.exception("Erro no loop de envio")
        await asyncio.sleep(30)
