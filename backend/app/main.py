import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import convites, gestao, integracoes, organizador, webhooks
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()
app = FastAPI(title="Bora API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origens,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(convites.router)
app.include_router(organizador.router)
app.include_router(gestao.router)
app.include_router(integracoes.router)
app.include_router(webhooks.router)


@app.get("/health", tags=["infra"])
async def health() -> dict:
    return {"status": "ok", "ambiente": settings.ambiente}
