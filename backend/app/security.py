"""Autenticação do organizador via JWT do Supabase Auth.

O Angular faz login no Supabase e envia `Authorization: Bearer <access_token>`.
Suporta as chaves assimétricas novas (JWKS) e o segredo HS256 legado.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import jwt
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Organizador:
    id: UUID
    email: str | None


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    url = get_settings().supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
    return jwt.PyJWKClient(url, cache_keys=True)


def decodificar_token(token: str) -> dict:
    settings = get_settings()
    cabecalho = jwt.get_unverified_header(token)
    if cabecalho.get("alg") == "HS256":
        if not settings.supabase_jwt_secret:
            raise jwt.InvalidTokenError("SUPABASE_JWT_SECRET não configurado")
        chave = settings.supabase_jwt_secret
        algoritmos = ["HS256"]
    else:
        chave = _jwks_client().get_signing_key_from_jwt(token).key
        algoritmos = ["RS256", "ES256"]
    return jwt.decode(token, chave, algorithms=algoritmos, audience="authenticated")


async def organizador_atual(
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Organizador:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Não autenticado")
    try:
        claims = decodificar_token(cred.credentials)
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido") from e
    return Organizador(id=UUID(claims["sub"]), email=claims.get("email"))


OrganizadorAtual = Annotated[Organizador, Depends(organizador_atual)]


# ---------------------------------------------------------------------------
# Tokens e criptografia
# ---------------------------------------------------------------------------
def gerar_token_convite() -> str:
    """Token do link do convidado: 32 bytes aleatórios (256 bits), URL-safe."""
    return secrets.token_urlsafe(32)


def _fernet() -> Fernet:
    chave = get_settings().chave_criptografia
    if not chave:
        raise RuntimeError("CHAVE_CRIPTOGRAFIA não configurada")
    return Fernet(chave)


def criptografar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def descriptografar(texto: str) -> str:
    return _fernet().decrypt(texto.encode()).decode()


# ---------------------------------------------------------------------------
# "state" do OAuth do Mercado Pago: identifica o organizador no callback
# (criptografado + com validade, para não ser forjado nem reaproveitado depois)
# ---------------------------------------------------------------------------
STATE_VALIDADE_S = 600


def gerar_state_oauth(organizador_id: UUID) -> str:
    return criptografar(f"{organizador_id}:{secrets.token_hex(8)}")


def validar_state_oauth(state: str) -> UUID:
    """Retorna o id do organizador ou levanta ValueError se inválido/expirado."""
    from cryptography.fernet import InvalidToken

    try:
        texto = _fernet().decrypt(state.encode(), ttl=STATE_VALIDADE_S).decode()
    except InvalidToken as e:
        raise ValueError("state inválido ou expirado") from e
    return UUID(texto.split(":", 1)[0])
