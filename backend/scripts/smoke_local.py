"""Teste de fumaça ponta a ponta contra o ambiente LOCAL (supabase start + uvicorn).

Percorre o fluxo principal pela API real:
  organizador se cadastra → cria evento + colaboração → conecta MP (falso) → adiciona
  convidados → ativa → convidado abre o link / responde → baixa manual → painel →
  webhook com assinatura inválida → aprovação de pagamento via serviço (como o webhook faria).

Uso (na pasta backend, com a API rodando em :8000):
  uv run python scripts/smoke_local.py

Lê SUPABASE_URL, ANON_KEY e SERVICE_ROLE_KEY do ambiente
(gere com: npx supabase status -o env).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

API = os.environ.get("API_URL", "http://localhost:8000")
SB = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54321")
ANON = os.environ["ANON_KEY"]
SERVICE = os.environ["SERVICE_ROLE_KEY"]

ok = 0


def check(cond: bool, msg: str) -> None:
    global ok
    if not cond:
        print(f"  FALHOU: {msg}")
        sys.exit(1)
    ok += 1
    print(f"  ok  {msg}")


def rest(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=f"{SB}/rest/v1",
        headers={
            "apikey": ANON if token != SERVICE else SERVICE,
            "Authorization": f"Bearer {token}",
            "Prefer": "return=representation",
        },
        timeout=20,
    )


def main() -> None:
    print("1. Organizador se cadastra no Supabase Auth")
    sufixo = uuid.uuid4().hex[:8]
    email = f"teste-{sufixo}@bora.local"
    nome_evento = f"Festa de Teste {sufixo}"
    r = httpx.post(
        f"{SB}/auth/v1/signup",
        headers={"apikey": ANON},
        json={"email": email, "password": "senha-teste-123", "data": {"nome": "Isac Teste"}},
    )
    check(r.status_code == 200 and r.json().get("access_token"), f"cadastro ({r.status_code})")
    jwt = r.json()["access_token"]
    org_id = r.json()["user"]["id"]
    api = httpx.Client(base_url=API, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)

    r = api.get("/eu")
    check(
        r.status_code == 200 and r.json()["id"] == org_id, f"/eu reconhece o JWT ({r.status_code})"
    )
    check(r.json()["mercado_pago_conectado"] is False, "MP ainda não conectado")

    print("2. Cria evento + colaboração direto no Supabase (RLS)")
    db = rest(jwt)
    data_evento = (datetime.now(UTC) + timedelta(days=60)).replace(hour=22, minute=0, second=0)
    r = db.post(
        "/evento",
        json={
            "organizador_id": org_id,
            "nome": nome_evento,
            "data_hora": data_evento.isoformat(),
            "local_nome": "Chácara",
            "tem_contribuicao": True,
            "max_acompanhantes": 2,
        },
    )
    check(r.status_code == 201, f"evento criado ({r.status_code} {r.text[:200]})")
    ev_id = r.json()[0]["id"]
    r = db.post(
        "/colaboracao",
        json={
            "evento_id": ev_id,
            "descricao": "Aluguel",
            "tipo": "RATEIO",
            "meta": 800,
            "pessoas_estimadas": 27,
        },
    )
    check(r.status_code == 201, "colaboração RATEIO 800/27 criada")

    outro = rest(ANON)
    r = outro.get("/evento", params={"id": f"eq.{ev_id}"})
    check(r.status_code == 200 and r.json() == [], "anônimo NÃO vê o evento (RLS)")

    print("3. Convidados antes de ativar")
    r = api.post(
        f"/eventos/{ev_id}/convidados", json={"nome": "Ana Souza", "telefone": "(11) 98765-4321"}
    )
    check(r.status_code == 201, f"Ana adicionada ({r.status_code} {r.text[:200]})")
    ana = r.json()
    check(ana["telefone_e164"] == "+5511987654321", "telefone normalizado")
    check(
        ana["valor_por_pessoa"] == "30.00", f"rateio congelado em R$ 30 ({ana['valor_por_pessoa']})"
    )
    r = api.post(
        f"/eventos/{ev_id}/convidados", json={"nome": "Ana de novo", "telefone": "11987654321"}
    )
    check(r.status_code == 409, "telefone duplicado barrado")
    r = api.post(
        f"/eventos/{ev_id}/convidados", json={"nome": "Bruno", "telefone": "21 99876-5432"}
    )
    check(r.status_code == 201, "Bruno adicionado")
    bruno = r.json()
    r = api.post(f"/eventos/{ev_id}/convidados", json={"nome": "Inválido", "telefone": "123"})
    check(r.status_code == 422, "telefone inválido barrado")

    print("4. Ativar exige Mercado Pago conectado")
    r = api.post(f"/eventos/{ev_id}/ativar")
    check(r.status_code == 409, "ativar sem MP → 409")

    from app.security import criptografar  # usa CHAVE_CRIPTOGRAFIA do .env

    adm = rest(SERVICE)
    r = adm.post(
        "/integracao_mp",
        json={
            "organizador_id": org_id,
            "mp_user_id": "999",
            "access_token_enc": criptografar("TOKEN-FALSO"),
            "refresh_token_enc": criptografar("REFRESH-FALSO"),
            "expira_em": (datetime.now(UTC) + timedelta(days=180)).isoformat(),
        },
    )
    check(r.status_code == 201, f"integração MP falsa inserida ({r.status_code} {r.text[:200]})")

    r = api.post(f"/eventos/{ev_id}/ativar")
    check(r.status_code == 200, f"evento ativado ({r.status_code} {r.text[:200]})")
    check(r.json()["convites_enfileirados"] == 2, "2 convites na fila")
    check(
        r.json()["prazo_pagamento"] is not None, f"prazo calculado: {r.json()['prazo_pagamento']}"
    )

    r = adm.get("/mensagem", params={"select": "tipo,conteudo,status", "tipo": "eq.CONVITE"})
    convites = [m for m in r.json() if nome_evento in m["conteudo"]]
    check(
        len(convites) == 2 and all(m["status"] == "PENDENTE" for m in convites),
        "mensagens CONVITE pendentes",
    )
    print("     texto:", convites[0]["conteudo"].replace("\n", " / "))

    print("5. Convidado abre o link (público, sem login)")
    token_ana = ana["link"].rsplit("/", 1)[1]
    pub = httpx.Client(base_url=API, timeout=30)
    r = pub.get(f"/convites/{token_ana}")
    check(r.status_code == 200, "GET /convites/{token}")
    c = r.json()
    check(
        c["status"] == "CONVIDADO" and c["valor_cobrado"] == "30.30",
        f"R$ 30,30 com taxa ({c['valor_cobrado']})",
    )
    check(pub.get("/convites/token-que-nao-existe").status_code == 404, "token inválido → 404")

    r = pub.post(f"/convites/{token_ana}/resposta", json={"vou": True, "qtd_acompanhantes": 3})
    check(r.status_code == 422, "acima do máximo de acompanhantes → 422")
    r = pub.post(f"/convites/{token_ana}/resposta", json={"vou": True, "qtd_acompanhantes": 1})
    check(
        r.status_code == 200 and r.json()["status"] == "AGUARDANDO_PAGAMENTO",
        "Ana: Vou + 1 acompanhante",
    )
    check(
        r.json()["valor_devido"] == "60.00" and r.json()["valor_cobrado"] == "60.60",
        f"valor 2 pessoas: {r.json()['valor_devido']} → {r.json()['valor_cobrado']}",
    )

    token_bruno = bruno["link"].rsplit("/", 1)[1]
    r = pub.post(f"/convites/{token_bruno}/resposta", json={"vou": False})
    check(r.json()["status"] == "RECUSOU", "Bruno: Não vou")

    r = pub.post(f"/convites/{token_ana}/pagamento")
    check(r.status_code == 502, f"PIX com token MP falso falha como esperado ({r.status_code})")

    print("6. Baixa manual e painel")
    r = api.post(
        f"/eventos/{ev_id}/convidados/{ana['id']}/baixa-manual",
        json={"valor": 60, "observacao": "dinheiro"},
    )
    check(
        r.status_code == 200 and r.json()["status"] == "CONFIRMADO", "baixa manual confirma a Ana"
    )
    r = api.delete(f"/eventos/{ev_id}/convidados/{ana['id']}")
    check(r.status_code == 409, "não remove quem já pagou")

    r = api.get(f"/eventos/{ev_id}/painel")
    p = r.json()
    check(r.status_code == 200, "painel")
    check(p["por_status"] == {"CONFIRMADO": 1, "RECUSOU": 1}, f"contagem {p['por_status']}")
    check(p["pessoas_confirmadas"] == 2, "2 pessoas confirmadas (Ana + 1)")
    check(p["arrecadado_total"] == "60.00", f"arrecadado {p['arrecadado_total']}")
    check(p["colaboracoes"][0]["arrecadado"] == "60.00", "arrecadação por colaboração")

    r = api.get(f"/eventos/{ev_id}/convidados")
    check(r.status_code == 200 and len(r.json()) == 2, "lista de convidados")

    r = adm.get("/mensagem", params={"select": "tipo", "tipo": "eq.CONFIRMACAO"})
    check(len(r.json()) >= 1, "mensagem de CONFIRMACAO enfileirada")

    print("7. Webhook do MP")
    r = pub.post(
        "/webhooks/mercadopago",
        json={"type": "order", "data": {"id": "ORD1"}},
        headers={"x-signature": "ts=1,v1=errado", "x-request-id": "r1"},
    )
    check(r.status_code == 401, "assinatura inválida → 401")

    print("8. Aprovação de pagamento (o que o webhook faz depois de consultar o MP)")
    r = pub.post(f"/convites/{token_bruno}/resposta", json={"vou": True, "qtd_acompanhantes": 0})
    check(r.json()["status"] == "AGUARDANDO_PAGAMENTO", "Bruno mudou de ideia: Vou")
    r = adm.post(
        "/pagamento",
        json={
            "convidado_id": bruno["id"],
            "valor_liquido": 30,
            "valor_cobrado": 30.3,
            "mp_order_id": "ORD-TESTE-1",
            "expira_em": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    check(r.status_code == 201, "cobrança pendente simulada")

    async def aprovar():
        from app.db import get_sessionmaker
        from app.services.pagamentos import aplicar_status_pagamento

        async with get_sessionmaker()() as s:
            await aplicar_status_pagamento(s, mp_order_id="ORD-TESTE-1", novo_status="APROVADO")
            await aplicar_status_pagamento(
                s, mp_order_id="ORD-TESTE-1", novo_status="APROVADO"
            )  # idempotente

    asyncio.run(aprovar())
    r = pub.get(f"/convites/{token_bruno}")
    check(r.json()["status"] == "CONFIRMADO", "Bruno CONFIRMADO após pagamento aprovado")
    r = api.get(f"/eventos/{ev_id}/painel")
    check(
        r.json()["arrecadado_total"] == "90.00", f"arrecadado agora {r.json()['arrecadado_total']}"
    )

    print("9. Cancelamento")
    r = api.post(f"/eventos/{ev_id}/cancelar")
    check(r.status_code == 200 and r.json()["avisados"] == 2, "evento cancelado, 2 avisados")

    print(f"\nTUDO CERTO — {ok} verificações")


if __name__ == "__main__":
    main()
