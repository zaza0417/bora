"""Comprovante enviado pelo convidado no WhatsApp do organizador (modo PIX manual).

Quando chega uma imagem/PDF de um número que é convidado de um evento ATIVO do dono da
instância e ainda não está confirmado:
  1. baixa a mídia na Evolution e guarda no bucket privado "comprovantes";
  2. lê o texto (PDF direto ou OCR) e confere valor, data, recebedor, convidado e ID E2E;
  3. se o organizador ligou a baixa automática e tudo confere → confirma a presença;
     senão → entra na fila "Comprovantes para conferir" do painel;
  4. responde ao convidado pelo WhatsApp.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.comprovante import analisar
from app.domain.estados import TransicaoInvalida
from app.domain.mensagens import TipoMensagem
from app.domain.telefone import TelefoneInvalido, normalizar_telefone
from app.integrations.evolution import ErroEvolution, EventoMensagemRecebida, EvolutionClient
from app.services import ocr, storage
from app.services.mensageria import enfileirar_mensagem
from app.services.pagamentos import confirmar_pagamento_manual

log = logging.getLogger(__name__)

EXTENSOES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}


@dataclass
class Midia:
    conteudo: bytes
    mimetype: str
    caminho: str | None  # None se não deu para guardar no Storage


async def processar_comprovante(sessao: AsyncSession, ev: EventoMensagemRecebida) -> str:
    """Retorna um código curto do que aconteceu (para log/teste)."""
    try:
        telefone = normalizar_telefone("+" + ev.remetente)
    except TelefoneInvalido:
        return "numero_invalido"

    cand = (
        (
            await sessao.execute(
                text("""
                    select c.id, c.nome, c.evento_id, c.valor_devido, c.convidado_em,
                           o.pix_nome, o.baixa_automatica
                      from convidado c
                      join evento e on e.id = c.evento_id
                      join organizador o on o.id = e.organizador_id
                      join integracao_whatsapp w on w.organizador_id = e.organizador_id
                     where w.instancia = :inst and c.telefone_e164 = :tel
                       and e.status = 'ATIVO' and e.tem_contribuicao
                       and c.status in ('CONVIDADO', 'AGUARDANDO_PAGAMENTO')
                     order by e.data_hora
                     limit 1
                     for update of c
                """),
                {"inst": ev.instancia, "tel": telefone},
            )
        )
        .mappings()
        .first()
    )
    if cand is None:
        return "nao_e_convidado_pendente"

    ja = await sessao.execute(
        text("select 1 from convidado where comprovante_mensagem_id = :m"), {"m": ev.id_mensagem}
    )
    if ja.first():
        return "duplicado"

    midia = await _baixar_e_guardar(ev, cand["evento_id"], cand["id"])
    analise = await _conferir(sessao, cand, midia)

    await sessao.execute(
        text("""
            update convidado
               set comprovante_path = :p, comprovante_recebido_em = now(),
                   comprovante_mensagem_id = :m, comprovante_analise = cast(:a as jsonb),
                   comprovante_e2e = :e2e
             where id = :id
        """),
        {
            "p": midia.caminho if midia else None,
            "m": ev.id_mensagem,
            "a": _json(analise.para_json()) if analise else None,
            # repetido → não grava (o índice único barraria) e fica marcado na análise
            "e2e": analise.e2e if analise and not analise.repetido else None,
            "id": cand["id"],
        },
    )

    if analise and analise.tudo_confere and cand["baixa_automatica"]:
        try:
            await confirmar_pagamento_manual(
                sessao,
                convidado_id=cand["id"],
                valor=Decimal(cand["valor_devido"]),
                observacao="Baixa automática: comprovante conferido por OCR",
                comprovante_path=midia.caminho if midia else None,
            )
        except TransicaoInvalida:
            pass
        else:
            await sessao.commit()
            log.info("comprovante de %s conferido e confirmado automaticamente", cand["nome"])
            return "confirmado_automaticamente"

    await enfileirar_mensagem(sessao, cand["id"], TipoMensagem.COMPROVANTE_RECEBIDO)
    await sessao.commit()
    log.info(
        "comprovante recebido de %s (tudo confere: %s)",
        cand["nome"],
        analise.tudo_confere if analise else "sem leitura",
    )
    return "registrado"


async def _conferir(sessao: AsyncSession, cand, midia: Midia | None):
    if midia is None:
        return None
    texto = await asyncio.to_thread(ocr.extrair_texto, midia.conteudo, midia.mimetype)
    usados = set(
        (
            await sessao.execute(
                text(
                    "select comprovante_e2e from convidado "
                    "where comprovante_e2e is not null and id <> :id"
                ),
                {"id": cand["id"]},
            )
        ).scalars()
    )
    fuso = ZoneInfo(get_settings().fuso)
    return analisar(
        texto,
        valor_esperado=Decimal(cand["valor_devido"]),
        nome_convidado=cand["nome"],
        nome_recebedor=cand["pix_nome"],
        desde=cand["convidado_em"].astimezone(fuso).date(),
        hoje=datetime.now(fuso).date(),
        e2e_ja_usados=usados,
    )


async def _baixar_e_guardar(
    ev: EventoMensagemRecebida, evento_id: UUID, convidado_id: UUID
) -> Midia | None:
    """Baixa da Evolution e sobe no Storage. Sem mídia, o organizador ainda vê o
    comprovante no próprio WhatsApp e confere à mão."""
    try:
        dados = await EvolutionClient.from_settings().baixar_midia(ev.instancia, ev.chave_mensagem)
        conteudo = base64.b64decode(dados["base64"])
        tipo = (dados.get("mimetype") or "image/jpeg").split(";")[0]
    except (ErroEvolution, KeyError, ValueError) as e:
        log.warning("não foi possível baixar a mídia do comprovante: %s", e)
        return None

    caminho = f"{evento_id}/{convidado_id}/{ev.id_mensagem}.{EXTENSOES.get(tipo, 'bin')}"
    try:
        await storage.enviar(storage.BUCKET_COMPROVANTES, caminho, conteudo, tipo)
    except storage.ErroStorage as e:
        log.warning("não foi possível guardar o comprovante: %s", e)
        caminho = None
    return Midia(conteudo, tipo, caminho)


def _json(d: dict) -> str:
    import json

    return json.dumps(d, ensure_ascii=False)
