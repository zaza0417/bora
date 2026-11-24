"""Comprovante enviado pelo convidado no WhatsApp do organizador (modo PIX manual).

Quando chega uma imagem/PDF de um número que é convidado de um evento ATIVO do dono da
instância e ainda não está confirmado:
  1. baixa a mídia na Evolution e lê o texto (PDF direto ou OCR);
  2. decide (domain/comprovante.destino): foto/meme/print → ignora, sem guardar nem
     responder; parece comprovante mas o valor não bate → fila do organizador, sem
     responder; é o comprovante deste pagamento → segue;
  3. guarda no bucket privado "comprovantes";
  4. se o organizador ligou a baixa automática e tudo confere → confirma a presença;
     senão → entra na fila "Comprovantes para conferir" do painel;
  5. responde ao convidado pelo WhatsApp uma vez só (recebido, ou presença confirmada).
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
from app.domain.comprovante import Destino, analisar, destino
from app.domain.estados import TransicaoInvalida
from app.domain.mensagens import TipoMensagem
from app.domain.telefone import TelefoneInvalido, normalizar_telefone
from app.integrations.evolution import ErroEvolution, EventoMensagemRecebida, EvolutionClient
from app.services import ocr, storage
from app.services.cobranca import SQL_VALOR_PAGO
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
                text(f"""
                    select c.id, c.nome, c.evento_id, c.convidado_em,
                           c.valor_devido - {SQL_VALOR_PAGO} as falta_pagar,
                           c.comprovante_recebido_em is not null
                             and coalesce((c.comprovante_analise->>'valor_confere')::boolean, false)
                             and not coalesce((c.comprovante_analise->>'repetido')::boolean, false)
                             as ja_tem_o_certo,
                           c.comprovante_path as comprovante_anterior,
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

    # Primeiro lê; só depois decide se é o comprovante e se responde ao convidado
    midia = await _baixar(ev)
    analise = await _conferir(sessao, cand, midia)
    para_onde = destino(analise, ja_tem_o_certo=cand["ja_tem_o_certo"])
    if para_onde is Destino.IGNORAR:
        log.info(
            "imagem de %s ignorada (%s)",
            cand["nome"],
            "já há comprovante certo" if cand["ja_tem_o_certo"] else "não é comprovante",
        )
        return "ignorado"

    if midia:
        midia.caminho = await _guardar(midia, ev, cand["evento_id"], cand["id"])
    await _apagar_anterior(sessao, cand, midia.caminho if midia else None)

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
                valor=Decimal(cand["falta_pagar"]),
                observacao="Baixa automática: comprovante conferido por OCR",
                comprovante_path=midia.caminho if midia else None,
            )
        except TransicaoInvalida:
            pass
        else:
            await sessao.commit()
            log.info("comprovante de %s conferido e confirmado automaticamente", cand["nome"])
            return "confirmado_automaticamente"

    # Avisa o convidado só quando é mesmo o comprovante deste pagamento (uma vez)
    if para_onde is Destino.RECEBIDO:
        await enfileirar_mensagem(sessao, cand["id"], TipoMensagem.COMPROVANTE_RECEBIDO)
    await sessao.commit()
    log.info(
        "comprovante de %s: %s (tudo confere: %s)",
        cand["nome"],
        para_onde.value,
        analise.tudo_confere if analise else "sem leitura",
    )
    return "registrado" if para_onde is Destino.RECEBIDO else "para_conferir"


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
        valor_esperado=Decimal(cand["falta_pagar"]),
        nome_convidado=cand["nome"],
        nome_recebedor=cand["pix_nome"],
        desde=cand["convidado_em"].astimezone(fuso).date(),
        hoje=datetime.now(fuso).date(),
        e2e_ja_usados=usados,
    )


async def _baixar(ev: EventoMensagemRecebida) -> Midia | None:
    """Baixa da Evolution. Sem mídia, o organizador ainda vê o comprovante no próprio
    WhatsApp e confere à mão."""
    try:
        dados = await EvolutionClient.from_settings().baixar_midia(ev.instancia, ev.chave_mensagem)
        conteudo = base64.b64decode(dados["base64"])
        tipo = (dados.get("mimetype") or "image/jpeg").split(";")[0]
    except (ErroEvolution, KeyError, ValueError) as e:
        log.warning("não foi possível baixar a mídia do comprovante: %s", e)
        return None
    return Midia(conteudo, tipo, None)


async def _guardar(
    midia: Midia, ev: EventoMensagemRecebida, evento_id: UUID, convidado_id: UUID
) -> str | None:
    """Sobe no bucket privado só o que vai para a fila (fotos e memes não são guardados)."""
    caminho = f"{evento_id}/{convidado_id}/{ev.id_mensagem}.{EXTENSOES.get(midia.mimetype, 'bin')}"
    try:
        await storage.enviar(storage.BUCKET_COMPROVANTES, caminho, midia.conteudo, midia.mimetype)
    except storage.ErroStorage as e:
        log.warning("não foi possível guardar o comprovante: %s", e)
        return None
    return caminho


async def _apagar_anterior(sessao: AsyncSession, cand, caminho_novo: str | None) -> None:
    """O comprovante novo substitui o anterior (que não batia): não deixa arquivo órfão.

    Nunca apaga um comprovante que já virou pagamento (ex.: pagou, depois aumentou os
    acompanhantes e agora manda o da diferença).
    """
    anterior = cand["comprovante_anterior"]
    if not anterior or anterior == caminho_novo or cand["ja_tem_o_certo"]:
        return
    usado = await sessao.execute(
        text("select 1 from pagamento where comprovante_path = :p"), {"p": anterior}
    )
    if usado.first():
        return
    try:
        await storage.apagar(storage.BUCKET_COMPROVANTES, anterior)
    except storage.ErroStorage as e:
        log.warning("não foi possível apagar o comprovante anterior: %s", e)


def _json(d: dict) -> str:
    import json

    return json.dumps(d, ensure_ascii=False)
