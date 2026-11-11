"""Supabase Storage pelo backend (service role) — bucket privado de comprovantes."""

from __future__ import annotations

import httpx

from app.config import get_settings

BUCKET_COMPROVANTES = "comprovantes"


class ErroStorage(Exception):
    pass


def _base() -> tuple[str, dict[str, str]]:
    s = get_settings()
    if not s.supabase_service_role_key:
        raise ErroStorage("SUPABASE_SERVICE_ROLE_KEY não configurada")
    chave = s.supabase_service_role_key
    cab = {"Authorization": f"Bearer {chave}", "apikey": chave}
    return s.supabase_url.rstrip("/") + "/storage/v1", cab


async def enviar(bucket: str, caminho: str, conteudo: bytes, content_type: str) -> str:
    base, cab = _base()
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.post(
            f"{base}/object/{bucket}/{caminho}",
            content=conteudo,
            headers={**cab, "Content-Type": content_type, "x-upsert": "true"},
        )
    if r.status_code >= 400:
        raise ErroStorage(f"upload falhou: {r.status_code} {r.text[:300]}")
    return caminho


async def url_assinada(bucket: str, caminho: str, segundos: int = 3600) -> str:
    base, cab = _base()
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.post(
            f"{base}/object/sign/{bucket}/{caminho}", json={"expiresIn": segundos}, headers=cab
        )
    if r.status_code >= 400:
        raise ErroStorage(f"assinatura falhou: {r.status_code} {r.text[:300]}")
    return f"{base}{r.json()['signedURL']}"
