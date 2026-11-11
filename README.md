# Bora — plataforma de eventos

Organize eventos, convide pelo WhatsApp e receba as contribuições via PIX (Mercado Pago),
com confirmação de presença automática. Requisitos completos em [docs/requisitos.md](docs/requisitos.md).

```
frontend/   Angular 22 (organizador + página pública do convidado) → Vercel
backend/    FastAPI + worker (fila WhatsApp, lembretes)           → VM com Docker
supabase/   migrations do Postgres (schema + RLS + storage)       → Supabase
infra/      docker-compose (API, worker, Evolution API, Caddy)
docs/       requisitos
```

## Rodando localmente

Pré-requisitos: Python 3.13 + [uv](https://docs.astral.sh/uv/), Node 22, Docker Desktop,
[Supabase CLI](https://supabase.com/docs/guides/local-development).

### 1. Banco (Supabase local)

```bash
supabase init        # só na primeira vez; mantém a pasta supabase/migrations
supabase start       # sobe Postgres/Auth/Storage e aplica as migrations
```

Anote a `anon key` e a `API URL` exibidas.

### 2. Backend

```bash
cd backend
cp .env.example .env     # preencha CHAVE_CRIPTOGRAFIA etc.
uv sync
uv run uvicorn app.main:app --reload        # API em http://localhost:8000/docs
uv run python -m app.worker                 # worker (outro terminal)
uv run pytest                               # testes das regras de negócio
```

> **Windows:** se o caminho da pasta for muito longo (> 260 caracteres), pacotes como o
> `pydantic-core` falham ao importar. Use um ambiente virtual num caminho curto:
> `set UV_PROJECT_ENVIRONMENT=C:\venvs\eventos` antes do `uv sync`.

### 3. Frontend

```bash
cd frontend
npm install
# edite src/environments/environment.development.ts com a anon key do passo 1
npm start                                   # http://localhost:4200
```

Página do convidado: `http://localhost:4200/c/<token>`.

### 4. WhatsApp (Evolution API) local

```bash
cd infra
cp .env.example .env
docker compose up -d evolution evolution-db evolution-redis
```

## Deploy

| Parte | Onde | Como |
|---|---|---|
| Frontend | Vercel | Importar o repositório, *Root Directory* = `frontend` (usa `vercel.json`) |
| Banco/Auth/Storage | Supabase | `supabase link` + `supabase db push` |
| API + worker + WhatsApp | VM (Oracle Cloud Always Free) | `cd infra && docker compose up -d --build` |

Webhook do Mercado Pago: `https://<API_DOMINIO>/webhooks/mercadopago`.

## Estado atual (projeto base)

Pronto:
- Schema completo + RLS + buckets de storage (validados num Postgres de teste)
- Regras de negócio com testes: prazo de pagamento, rateio/taxa, máquina de estados, telefone, mensagens, assinatura do webhook
- API: página do convidado (ver/responder/pagar/status), ativar evento, cadastrar convidado, webhook do MP
- Worker: fila de envio (janela 9h–20h, intervalo aleatório, imagem do convite), lembretes, expiração de PIX
- API de gestão: listar/reenviar/remover convidados, baixa manual, painel, cancelar evento, recalcular prazo
- Angular: login, lista de eventos, criar/editar evento (arte do convite, colaborações com prévia do valor, atrações, cardápio), tela do evento (painel, arrecadação, convidados com filtros e ações) e página do convidado completa
- Configurações: conectar Mercado Pago (OAuth, tokens criptografados, renovação automática) e WhatsApp (QR Code com atualização automática, status por webhook)
- Jobs: renovação do token do MP, sincronização do status do WhatsApp, reconciliação de pagamentos pendentes

Próximos passos (ver roadmap em docs/requisitos.md §9):
- Testar ponta a ponta com Supabase local (`supabase start`)
- Otimização: carregar o supabase-js só nas telas do organizador (o convidado não precisa dele)
- Testar o OAuth do MP com uma aplicação real (precisa de URL pública HTTPS — ex.: túnel)
- Testar o WhatsApp com a Evolution rodando e um celular lendo o QR
- Validar na prática a Orders API do MP (payload PIX, e-mail do pagador, status)
