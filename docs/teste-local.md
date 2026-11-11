# Teste local

Ambiente: `npx supabase start -x studio,logflare,vector,edge-runtime,imgproxy,postgres-meta,realtime,supavisor,mailpit`
+ servidores `api` e `frontend` do `.claude/launch.json`.

## Conta de teste do organizador (só no Supabase LOCAL)

| E-mail | Senha |
|---|---|
| organizador@bora.local | bora-teste-local-2026 |

Crie pela tela "Criar uma conta" em http://localhost:4200/login (a confirmação de e-mail está
desligada no `supabase/config.toml`). Nunca use essa senha em produção.

## Teste de fumaça da API

```bash
cd backend
# exporte ANON_KEY, SERVICE_ROLE_KEY e SUPABASE_URL (npx supabase status -o env)
PYTHONIOENCODING=utf-8 uv run python scripts/smoke_local.py
```

## Mercado Pago simulado (sem credenciais)

`backend/scripts/mock_mercadopago.py` imita o OAuth, a Orders API (PIX) e o webhook assinado.
Nada sai do computador e nenhum dinheiro é movimentado.

1. Suba o servidor `mp-simulador` do `.claude/launch.json` (porta 8090).
2. No `backend/.env`: `MP_API_BASE` e `MP_AUTH_BASE` = `http://localhost:8090`
   (`MP_CLIENT_ID`/`MP_CLIENT_SECRET` podem ser qualquer valor).
3. Configurações → **Conectar Mercado Pago** → tela falsa "Autorizar".
4. Na página do convidado: **Vou!** → **Pagar com PIX**.
5. Em http://localhost:8090/simular clique **Pagar** (ou Expirar / Estornar):
   o simulador envia o webhook assinado e o convidado vira CONFIRMADO.

Para usar o Mercado Pago real, volte `MP_API_BASE=https://api.mercadopago.com`,
`MP_AUTH_BASE=https://auth.mercadopago.com.br` e preencha as credenciais da sua aplicação.
