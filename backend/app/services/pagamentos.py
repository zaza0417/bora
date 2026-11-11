"""Confirmação de pagamentos (webhook + reconciliação)."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.estados import AcaoConvidado, StatusConvidado, TransicaoInvalida, transicionar
from app.domain.mensagens import TipoMensagem
from app.integrations.mercadopago import MercadoPagoClient
from app.security import descriptografar
from app.services.mensageria import enfileirar_mensagem

log = logging.getLogger(__name__)

# Status da order no MP → status interno do pagamento.
# TODO: confirmar a lista de status da Orders API (ex.: "processed" = pago).
STATUS_MP = {
    "processed": "APROVADO",
    "expired": "EXPIRADO",
    "canceled": "CANCELADO",
    "refunded": "ESTORNADO",
    "charged_back": "ESTORNADO",
}


async def processar_order_mp(sessao: AsyncSession, *, order_id: str, mp_user_id: str) -> None:
    integ = (
        await sessao.execute(
            text("select access_token_enc from integracao_mp where mp_user_id = :uid"),
            {"uid": mp_user_id},
        )
    ).first()
    if integ is None:
        log.warning("Webhook MP para conta desconhecida: %s", mp_user_id)
        return

    mp = MercadoPagoClient(
        access_token=descriptografar(integ[0]), base_url=get_settings().mp_api_base
    )
    order = await mp.consultar_order(order_id)
    novo_status = STATUS_MP.get(order.status)
    if novo_status is None:
        return  # ainda pendente / status intermediário

    await aplicar_status_pagamento(sessao, mp_order_id=order_id, novo_status=novo_status)


async def aplicar_status_pagamento(
    sessao: AsyncSession, *, mp_order_id: str, novo_status: str
) -> None:
    pag = (
        (
            await sessao.execute(
                text("""
                select p.id, p.status, p.tipo, p.convidado_id, c.status as convidado_status,
                       e.tem_contribuicao
                  from pagamento p
                  join convidado c on c.id = p.convidado_id
                  join evento e on e.id = c.evento_id
                 where p.mp_order_id = :oid
                 for update of p, c
            """),
                {"oid": mp_order_id},
            )
        )
        .mappings()
        .first()
    )
    if pag is None or pag["status"] == novo_status:
        return  # desconhecido ou já processado (idempotente)

    await sessao.execute(
        text("""
            update pagamento
               set status = cast(:st as status_pagamento),
                   pago_em = case when cast(:st as status_pagamento) = 'APROVADO'
                                  then now() else pago_em end
             where id = :id
        """),
        {"st": novo_status, "id": pag["id"]},
    )

    if pag["tipo"] != "CONTRIBUICAO":
        await sessao.commit()
        return

    acao = {
        "APROVADO": AcaoConvidado.PAGAMENTO_APROVADO,
        "ESTORNADO": AcaoConvidado.ESTORNO,
    }.get(novo_status)
    if acao is not None:
        try:
            novo_convidado = transicionar(
                StatusConvidado(pag["convidado_status"]),
                acao,
                tem_contribuicao=pag["tem_contribuicao"],
            )
        except TransicaoInvalida:
            log.warning("Transição ignorada: %s / %s", pag["convidado_status"], acao)
        else:
            await sessao.execute(
                text("""
                    update convidado
                       set status = cast(:st as status_convidado),
                           confirmado_em = case when cast(:st as status_convidado) = 'CONFIRMADO'
                                                then now() else null end
                     where id = :id
                """),
                {"st": novo_convidado.value, "id": pag["convidado_id"]},
            )
            if novo_convidado is StatusConvidado.CONFIRMADO:
                await enfileirar_mensagem(sessao, pag["convidado_id"], TipoMensagem.CONFIRMACAO)

    await sessao.commit()


async def confirmar_pagamento_manual(
    sessao: AsyncSession,
    *,
    convidado_id,
    valor,
    observacao: str | None,
    comprovante_path: str | None = None,
) -> StatusConvidado:
    """Baixa manual (ou automática por OCR): registra o pagamento e confirma a presença.

    Não faz commit. Levanta TransicaoInvalida se o convidado não puder ser confirmado.
    """
    atual = (
        await sessao.execute(
            text("select status from convidado where id = :id for update"), {"id": convidado_id}
        )
    ).scalar_one()
    novo = transicionar(StatusConvidado(atual), AcaoConvidado.BAIXA_MANUAL, tem_contribuicao=True)
    await sessao.execute(
        text("""
            update pagamento set status = 'CANCELADO'
             where convidado_id = :id and tipo = 'CONTRIBUICAO' and status = 'PENDENTE'
        """),
        {"id": convidado_id},
    )
    await sessao.execute(
        text("""
            insert into pagamento (convidado_id, tipo, valor_liquido, valor_cobrado, origem,
                                   status, pago_em, observacao, comprovante_path)
            values (:id, 'CONTRIBUICAO', :v, :v, 'MANUAL', 'APROVADO', now(), :obs, :comp)
        """),
        {"id": convidado_id, "v": valor, "obs": observacao, "comp": comprovante_path},
    )
    await sessao.execute(
        text("update convidado set status = :st, confirmado_em = now() where id = :id"),
        {"st": novo.value, "id": convidado_id},
    )
    await enfileirar_mensagem(sessao, convidado_id, TipoMensagem.CONFIRMACAO)
    return novo
