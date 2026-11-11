from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Geral
    ambiente: str = "dev"
    fuso: str = "America/Sao_Paulo"
    url_publica_front: str = "http://localhost:4200"  # base dos links de convite
    url_publica_api: str = "http://localhost:8000"  # base para webhooks/OAuth callback
    cors_origens: list[str] = ["http://localhost:4200"]

    # Banco (Supabase → Project Settings → Database → Connection string; use o pooler)
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:54322/postgres"

    # Supabase Auth (validação do JWT do organizador)
    supabase_url: str = "http://localhost:54321"
    supabase_jwt_secret: str | None = None  # projetos com JWT legado (HS256)
    # Service role: só o backend usa (upload de comprovantes no bucket privado)
    supabase_service_role_key: str = ""

    # Criptografia dos tokens do Mercado Pago (Fernet). Gere com:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    chave_criptografia: str = ""

    # Mercado Pago (aplicação criada em mercadopago.com.br/developers)
    mp_client_id: str = ""
    mp_client_secret: str = ""
    mp_webhook_secret: str = ""
    mp_api_base: str = "https://api.mercadopago.com"
    mp_auth_base: str = "https://auth.mercadopago.com.br"  # simulador local: http://localhost:8090
    mp_taxa_pix: str = "0.0099"

    @property
    def mp_redirect_uri(self) -> str:
        """Precisa estar cadastrada na aplicação do MP (Suas integrações → Redirect URL)."""
        return self.url_publica_api.rstrip("/") + "/integracoes/mercadopago/callback"

    # Evolution API (WhatsApp não oficial)
    evolution_url: str = "http://evolution:8080"
    evolution_api_key: str = ""
    # Segredo que vai na URL do webhook da Evolution (?segredo=...) para validar a origem
    evolution_webhook_secret: str = ""
    # Base da URL do webhook vista pela Evolution (padrão: url_publica_api).
    # Local, com a Evolution no Docker: http://host.docker.internal:8000
    evolution_webhook_base: str | None = None

    # Envio de mensagens (RF-MSG-06)
    janela_envio_inicio: int = 9  # hora local
    janela_envio_fim: int = 20
    intervalo_envio_min_s: int = 8
    intervalo_envio_max_s: int = 25
    max_tentativas_envio: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
