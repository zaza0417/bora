"""Cliente da Evolution API (WhatsApp não oficial).

Uma instância por organizador (RF-ORG-04). Docs: https://doc.evolution-api.com
TODO: conferir os endpoints com a versão da Evolution usada no docker-compose.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import get_settings


class ErroEvolution(Exception):
    pass


@dataclass
class EvolutionClient:
    base_url: str
    api_key: str
    timeout: float = 20.0

    @classmethod
    def from_settings(cls) -> EvolutionClient:
        s = get_settings()
        return cls(base_url=s.evolution_url.rstrip("/"), api_key=s.evolution_api_key)

    async def _req(self, metodo: str, caminho: str, json: dict | None = None) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as cli:
                r = await cli.request(
                    metodo, f"{self.base_url}{caminho}", json=json, headers={"apikey": self.api_key}
                )
        except httpx.HTTPError as e:
            raise ErroEvolution(f"{metodo} {caminho} → sem conexão: {e}") from e
        if r.status_code >= 400:
            raise ErroEvolution(f"{metodo} {caminho} → {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else {}

    async def criar_instancia(
        self, instancia: str, webhook_url: str, headers: dict[str, str] | None = None
    ) -> dict:
        """Cria a instância e devolve o QR Code (base64) para o organizador escanear."""
        return await self._req(
            "POST",
            "/instance/create",
            {
                "instanceName": instancia,
                "integration": "WHATSAPP-BAILEYS",
                "qrcode": True,
                "webhook": {
                    "url": webhook_url,
                    "headers": headers or {},
                    "enabled": True,
                    "byEvents": False,
                    "base64": False,
                    "events": ["CONNECTION_UPDATE", "MESSAGES_UPDATE", "MESSAGES_UPSERT"],
                },
            },
        )

    async def qrcode(self, instancia: str) -> dict:
        return await self._req("GET", f"/instance/connect/{instancia}")

    async def estado(self, instancia: str) -> str:
        dados = await self._req("GET", f"/instance/connectionState/{instancia}")
        return dados.get("instance", {}).get("state", "unknown")  # "open" = conectado

    async def enviar_texto(self, instancia: str, numero: str, texto: str) -> str | None:
        """Envia texto. `numero` só com dígitos (ex.: 5511987654321). Retorna o id da mensagem."""
        dados = await self._req(
            "POST", f"/message/sendText/{instancia}", {"number": numero, "text": texto}
        )
        return (dados.get("key") or {}).get("id")

    async def enviar_imagem(
        self, instancia: str, numero: str, url_imagem: str, legenda: str = ""
    ) -> str | None:
        """Envia imagem (URL pública, ex.: Supabase Storage) com legenda."""
        dados = await self._req(
            "POST",
            f"/message/sendMedia/{instancia}",
            {
                "number": numero,
                "mediatype": "image",
                "media": url_imagem,
                "caption": legenda,
            },
        )
        return (dados.get("key") or {}).get("id")

    async def numero_conectado(self, instancia: str) -> str | None:
        """Número do WhatsApp conectado (ex.: '5511987654321'), se a Evolution informar."""
        try:
            dados = await self._req("GET", f"/instance/fetchInstances?instanceName={instancia}")
        except ErroEvolution:
            return None
        item = dados[0] if isinstance(dados, list) and dados else dados
        dono = (item or {}).get("ownerJid") or (item or {}).get("owner") or ""
        return dono.split("@", 1)[0] or None

    async def atualizar_webhook(
        self, instancia: str, url: str, headers: dict[str, str] | None = None
    ) -> None:
        """Reconfigura o webhook de uma instância já existente (novos eventos/segredo)."""
        await self._req(
            "POST",
            f"/webhook/set/{instancia}",
            {
                "webhook": {
                    "enabled": True,
                    "url": url,
                    "headers": headers or {},
                    "byEvents": False,
                    "base64": False,
                    "events": ["CONNECTION_UPDATE", "MESSAGES_UPDATE", "MESSAGES_UPSERT"],
                }
            },
        )

    async def baixar_midia(self, instancia: str, chave_mensagem: dict) -> dict:
        """Mídia de uma mensagem recebida: {'base64': ..., 'mimetype': ...}."""
        return await self._req(
            "POST",
            f"/chat/getBase64FromMediaMessage/{instancia}",
            {"message": {"key": chave_mensagem}, "convertToMp4": False},
        )

    async def desconectar(self, instancia: str) -> None:
        """Faz logout do número e apaga a instância."""
        try:
            await self._req("DELETE", f"/instance/logout/{instancia}")
        finally:
            await self._req("DELETE", f"/instance/delete/{instancia}")


# ---------------------------------------------------------------------------
# Webhook: interpretação dos eventos (função pura, testada em tests/)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EventoConexao:
    instancia: str
    status: str  # CONECTADO | AGUARDANDO_QR | DESCONECTADO


@dataclass(frozen=True)
class EventoMensagemRecebida:
    """Imagem/PDF recebido (possível comprovante)."""

    instancia: str
    remetente: str  # só dígitos, com DDI
    de_mim: bool
    id_mensagem: str
    chave_mensagem: dict
    tipo_midia: str  # imageMessage | documentMessage


@dataclass(frozen=True)
class EventoMensagem:
    id_mensagem: str
    status: str  # ENVIADA | ENTREGUE | LIDA


_ESTADOS = {"open": "CONECTADO", "connecting": "AGUARDANDO_QR", "close": "DESCONECTADO"}
_STATUS_MSG = {
    "SERVER_ACK": "ENVIADA",
    "DELIVERY_ACK": "ENTREGUE",
    "READ": "LIDA",
    "PLAYED": "LIDA",
}


TIPOS_COMPROVANTE = ("imageMessage", "documentMessage", "documentWithCaptionMessage")


def interpretar_evento(
    payload: dict,
) -> EventoConexao | EventoMensagem | EventoMensagemRecebida | None:
    """Aceita os nomes de evento da Evolution v2 ('connection.update') e o formato antigo."""
    nome = str(payload.get("event", "")).lower().replace("_", ".")
    dados = payload.get("data") or {}
    if nome == "connection.update":
        status = _ESTADOS.get(str(dados.get("state", "")).lower())
        instancia = payload.get("instance") or dados.get("instance")
        return EventoConexao(instancia, status) if status and instancia else None
    if nome == "messages.upsert":
        item = dados[0] if isinstance(dados, list) and dados else dados
        if not isinstance(item, dict):
            return None
        chave = item.get("key") or {}
        jid = str(chave.get("remoteJid", ""))
        if not jid.endswith("@s.whatsapp.net"):
            return None  # grupos (@g.us), LIDs, status etc.
        msg = item.get("message") or {}
        tipo = item.get("messageType") or next((t for t in TIPOS_COMPROVANTE if t in msg), "")
        if tipo not in TIPOS_COMPROVANTE or not chave.get("id"):
            return None
        return EventoMensagemRecebida(
            instancia=str(payload.get("instance") or ""),
            remetente=jid.split("@", 1)[0],
            de_mim=bool(chave.get("fromMe")),
            id_mensagem=str(chave["id"]),
            chave_mensagem=chave,
            tipo_midia=tipo,
        )
    if nome == "messages.update":
        item = dados[0] if isinstance(dados, list) and dados else dados
        if not isinstance(item, dict):
            return None
        id_msg = item.get("keyId") or (item.get("key") or {}).get("id")
        status = _STATUS_MSG.get(str(item.get("status", "")).upper())
        return EventoMensagem(id_msg, status) if id_msg and status else None
    return None
