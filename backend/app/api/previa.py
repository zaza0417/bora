"""Imagem da prévia do link do convite (o cartão que aparece no WhatsApp).

GET /previa/{token}.png → cartaz no tema do evento (app/domain/cartaz.py).
Usada pela página do convite (frontend/api/convite.ts) quando não há arte.
"""

from __future__ import annotations

import logging
import re
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.domain.cartaz import Fontes, desenhar_cartaz

log = logging.getLogger(__name__)
router = APIRouter(prefix="/previa", tags=["convidado"])
Sessao = Annotated[AsyncSession, Depends(get_session)]

# (família, peso) de cada papel; as fontes vêm da Google Fonts e ficam em memória
_FONTES = {
    "titulo_pesado": ("Bricolage Grotesque", 800),
    "titulo_leve": ("Bricolage Grotesque", 500),
    "titulo_serifa": ("Fraunces", 400),
    "texto": ("Geist", 500),
}
_cache: dict[str, bytes] = {}


async def _baixar_fonte(familia: str, peso: int) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            css = await cli.get(
                "https://fonts.googleapis.com/css2", params={"family": f"{familia}:wght@{peso}"}
            )
            achou = re.search(r"src: url\((.+?)\) format\('truetype'\)", css.text)
            if not achou:
                return None
            ttf = await cli.get(achou.group(1))
            ttf.raise_for_status()
            return ttf.content
    except httpx.HTTPError as e:
        log.warning("fonte %s %s indisponível: %s", familia, peso, e)
        return None


async def _fontes() -> Fontes:
    for papel, (familia, peso) in _FONTES.items():
        if papel not in _cache:
            dados = await _baixar_fonte(familia, peso)
            if dados:
                _cache[papel] = dados
    return Fontes(**{papel: _cache.get(papel) for papel in _FONTES})


@router.get("/{token}.png", response_class=Response)
async def previa(token: str, sessao: Sessao) -> Response:
    if not re.fullmatch(r"[\w-]{4,100}", token):
        raise HTTPException(404)
    ev = (
        (
            await sessao.execute(
                text("""
                select e.nome, e.data_hora, e.local_nome, e.tema
                  from convidado c join evento e on e.id = c.evento_id
                 where c.token = :t and e.status <> 'RASCUNHO'
            """),
                {"t": token},
            )
        )
        .mappings()
        .first()
    )
    if ev is None:
        raise HTTPException(404)
    png = desenhar_cartaz(
        nome=ev["nome"],
        data_hora=ev["data_hora"],
        local=ev["local_nome"],
        tema=ev["tema"],
        fontes=await _fontes(),
    )
    return Response(
        png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"},
    )
