# Bora — Requisitos (v1)

> Status: requisitos fechados para o MVP · 08/11/2026 · nome da plataforma: Bora

## 1. Visão geral

Plataforma para organizar eventos pessoais. O organizador cadastra o evento e os convidados; o sistema envia o convite pelo WhatsApp com um link único; o convidado se cadastra, informa acompanhantes e paga a contribuição via PIX (Mercado Pago). A presença é confirmada automaticamente quando o pagamento é aprovado. Quem não paga recebe lembretes mensais até o prazo.

**Público:** uso pessoal + algumas pessoas próximas (poucos organizadores).

### Atores
| Ator | Acesso | Faz o quê |
|---|---|---|
| Organizador | Login (Supabase Auth) | Cria eventos, convidados, colaborações; conecta seu WhatsApp e seu Mercado Pago |
| Convidado | Link único com token (sem login) | Vê o evento, confirma presença/acompanhantes, paga, escolhe presente |
| Sistema | Jobs e webhooks | Envia mensagens, cria cobranças, confirma pagamentos, envia lembretes |

### Fluxo principal
```
Organizador cria evento → cadastra convidado (nome + telefone)
  → WhatsApp (número do organizador) envia convite com link único
    → Convidado abre link → informa acompanhantes → "Vou" / "Não vou"
      → Evento sem contribuição: CONFIRMADO
      → Evento com contribuição: clica "Pagar" → PIX Mercado Pago (conta do organizador)
          → Webhook MP → pagamento aprovado → CONFIRMADO + mensagem de confirmação
          → Não pagou → lembrete a cada 30 dias até o prazo
```

---

## 2. Decisões tomadas

| Tema | Decisão |
|---|---|
| Pagamento | Mercado Pago, PIX dinâmico via API (Orders API), confirmação por webhook |
| Conta de recebimento | Cada organizador conecta a própria conta MP via OAuth; dinheiro cai direto nela |
| WhatsApp | API não oficial (Evolution API); cada organizador conecta o próprio número via QR Code |
| Taxa do MP (~0,99%) | Repassada ao convidado (R$ 30,00 → R$ 30,30) |
| Valor da contribuição | Modo **fixo por pessoa** ou **rateio** (meta ÷ pessoas estimadas, fixado no envio do convite) |
| Acompanhantes | Pagam o mesmo valor do convidado: total = valor × (1 + acompanhantes) |
| Pagamento parcial | Não existe pela plataforma; só via baixa manual |
| Prazo de pagamento | 5º dia útil do mês do evento (ou do mês anterior; ver RF-PZ) |
| Prazo vencido | Para de lembrar, mas **continua aceitando pagamento** |
| Feriados | Apenas nacionais |
| Stack | Python (FastAPI) · PostgreSQL/Auth/Storage no Supabase · Angular · Vercel (front) + VM grátis (backend + Evolution) |

---

## 3. Requisitos funcionais

### 3.1 Organizador e integrações (RF-ORG)
- **RF-ORG-01** Login de organizador via Supabase Auth. Cada organizador só vê os próprios eventos (RLS no Postgres).
- **RF-ORG-02** Tela de configurações: conectar **Mercado Pago** via OAuth (salvar access/refresh token criptografados, `user_id` do MP, validade).
- **RF-ORG-03** Renovar automaticamente o token do MP antes de expirar (validade de 6 meses); avisar o organizador se falhar.
- **RF-ORG-04** Tela de configurações: conectar **WhatsApp** lendo QR Code (uma instância da Evolution API por organizador). Mostrar status (conectado/desconectado).
- **RF-ORG-05** Avisar o organizador (no painel) quando o WhatsApp desconectar.
- **RF-ORG-06** Bloqueios: sem MP conectado não é possível ativar evento com contribuição; sem WhatsApp conectado os convites ficam na fila, sem envio.

### 3.2 Evento (RF-EVT)
- **RF-EVT-01** Cadastrar evento: nome, descrição, local (nome, endereço, link do mapa), data e hora, imagem de capa.
- **RF-EVT-02** Cadastrar **atrações** (nome, descrição, horário opcional).
- **RF-EVT-03** Cadastrar **cardápio/alimentação** (categoria, item, descrição).
- **RF-EVT-04** Definir se o evento **tem contribuição**.
- **RF-EVT-05** Definir o limite de acompanhantes por convidado (opcional).
- **RF-EVT-06** Estados do evento: `RASCUNHO → ATIVO → ENCERRADO`, ou `CANCELADO`. Convites só saem com o evento `ATIVO`.
- **RF-EVT-07** Cancelar o evento envia uma mensagem de cancelamento para todos os convidados que não recusaram.
- **RF-EVT-08** Editar o evento (data/local) permite, opcionalmente, notificar os convidados sobre a alteração.
- **RF-EVT-09** Subir uma **imagem/arte do convite** (JPG/PNG, até 5 MB). Ela é enviada no WhatsApp junto com o convite (o texto vira legenda) e aparece no topo da página do convidado. Sem arte, usa a capa; sem capa, só texto.

### 3.3 Colaborações (RF-COL)
- **RF-COL-01** Um evento pode ter várias colaborações (ex.: aluguel, bebidas). Campos: descrição, meta (opcional no modo fixo), tipo.
- **RF-COL-02** **Tipo FIXO:** valor por pessoa definido pelo organizador. O que passar da meta aparece como "sobra" no painel.
- **RF-COL-03** **Tipo RATEIO:** o organizador informa meta e **número estimado de pessoas**. Valor por pessoa = `ceil(meta ÷ pessoas_estimadas)` (arredondado para cima, em reais inteiros).
- **RF-COL-04** O valor por pessoa é **congelado no convidado no momento do envio do convite** (snapshot). Alterar a colaboração depois não muda o valor de quem já foi convidado.
- **RF-COL-05** Valor devido pelo convidado = `Σ valor_por_pessoa (colaborações) × (1 + acompanhantes)`.
- **RF-COL-06** Valor cobrado com taxa = `ceil_centavos(valor_devido ÷ (1 − taxa_mp))`, com `taxa_mp` configurável (padrão 0,99%). Ex.: 30,00 → 30,30.

### 3.4 Convidados (RF-CNV)
- **RF-CNV-01** Cadastrar convidado (nome + telefone) individualmente.
- **RF-CNV-02** Importar convidados em lote via CSV (nome, telefone).
- **RF-CNV-03** Normalizar o telefone para E.164 (+55DDDNÚMERO) e impedir duplicidade no mesmo evento.
- **RF-CNV-04** Gerar um **token único e não adivinhável** por convidado (link `/{token}`).
- **RF-CNV-05** Ao cadastrar o convidado num evento ATIVO, enfileirar o convite imediatamente.
- **RF-CNV-06** Reenviar o convite manualmente.
- **RF-CNV-07** Remover o convidado (cancela os lembretes e as cobranças pendentes).
- **RF-CNV-08** Estados do convidado:
  - `CONVIDADO`: convite enviado, ainda não respondeu
  - `AGUARDANDO_PAGAMENTO`: disse "Vou", evento com contribuição, ainda não pagou
  - `CONFIRMADO`: pagou, ou disse "Vou" num evento sem contribuição, ou teve baixa manual
  - `RECUSOU`: disse "Não vou"
  - Flag derivada `prazo_vencido` (não é um estado): hoje > prazo e não confirmado.

### 3.5 Página do convidado (RF-PAG)
- **RF-PAG-01** Página mobile-first acessada pelo link único: capa, data/hora, local com mapa, atrações, cardápio, presentes, colaborações e valor devido.
- **RF-PAG-02** O convidado confirma o nome e informa a quantidade de acompanhantes (respeitando o limite). O valor é recalculado na hora.
- **RF-PAG-03** Botões **"Vou"** e **"Não vou"**. "Não vou" interrompe os lembretes; o convidado pode mudar de ideia depois.
- **RF-PAG-04** Mudar a quantidade de acompanhantes depois de confirmado gera uma cobrança da diferença (se aumentar). Diminuir após pagar não gera reembolso automático (o organizador resolve manualmente).
- **RF-PAG-05** Opção de parar de receber mensagens (opt-out, LGPD).

### 3.6 Pagamento (RF-PGT)
- **RF-PGT-01** O botão "Pagar" cria uma cobrança PIX dinâmica na conta MP do organizador, com `external_reference` = id do pagamento interno.
- **RF-PGT-02** Exibir QR Code + PIX copia-e-cola + valor (com taxa). O QR expira em 24 h; se expirar, gera um novo ao clicar de novo.
- **RF-PGT-03** A página atualiza o status sozinha (polling ou Supabase Realtime) e mostra "Pagamento confirmado!".
- **RF-PGT-04** Webhook do MP: validar a assinatura, **consultar o pagamento na API** (não confiar só no payload), processar de forma **idempotente** (id externo único).
- **RF-PGT-05** Pagamento aprovado → convidado `CONFIRMADO` + mensagem de confirmação no WhatsApp.
- **RF-PGT-06** Estorno/chargeback → convidado volta para `AGUARDANDO_PAGAMENTO` e o organizador é avisado.
- **RF-PGT-07** Pagamento após o prazo é aceito normalmente.
- **RF-PGT-08** **Baixa manual** pelo organizador (dinheiro, PIX por fora), com valor, observação e comprovante opcional (Supabase Storage, bucket privado).
- **RF-PGT-09** Uma cobrança pendente por convidado e por tipo: gerar uma nova cancela a anterior.

### 3.6.1 PIX manual com comprovante (modo padrão, sem gateway)
- **RF-PGT-10** O organizador cadastra a chave PIX, o nome do recebedor e a cidade. Se não houver Mercado Pago conectado, o evento usa esse modo, sem taxa.
- **RF-PGT-11** A página do convidado gera um **PIX copia-e-cola** (BR Code do BCB) com o valor exato e um identificador do convidado (`BORA…`), e oferece um botão para enviar o comprovante no WhatsApp do organizador, com o texto pronto.
- **RF-PGT-12** Imagem ou PDF recebido no WhatsApp do organizador, vindo de um convidado pendente, é guardado (bucket privado), lido (texto do PDF ou OCR com Tesseract, sem IA) e conferido: **valor**, **data** (entre o convite e hoje), **recebedor** (nome do PIX do organizador), **nome do convidado** (só informativo, outra pessoa pode pagar) e **ID E2E** não repetido.
- **RF-PGT-13** O comprovante entra na fila **"Comprovantes para conferir"** do painel, com a imagem e o resultado da conferência. O organizador confirma (baixa manual) ou descarta. Com a **baixa automática** ligada (Configurações, desligada por padrão), a presença é confirmada sozinha quando valor, data e recebedor conferem e o comprovante não é repetido.

### 3.7 Prazo de pagamento (RF-PZ)
- **RF-PZ-01** `d5 = 5º dia útil do mês do evento`.
- **RF-PZ-02** Se `data_evento ≤ d5` → `prazo = 5º dia útil do mês anterior`; senão `prazo = d5`.
- **RF-PZ-03** Se o prazo calculado já passou na criação/ativação do evento → `prazo = data_evento − 3 dias corridos`. Se isso também já passou → `prazo = data_evento`.
- **RF-PZ-04** Dia útil = segunda a sexta, exceto feriados nacionais (biblioteca `holidays`, BR).
- **RF-PZ-05** O prazo é calculado automaticamente e pode ser editado manualmente pelo organizador.

Exemplos (calendário 2026):
| Evento | 5º dia útil do mês | Prazo |
|---|---|---|
| 20/12/2026 | 07/12 (seg) | 07/12/2026 |
| 03/12/2026 | 07/12 → evento antes | 09/11/2026 (5º dia útil de nov; 02/11 é feriado) |
| 03/12/2026, criado em 20/11 | prazo de 09/11 já passou | 30/11/2026 (evento − 3 dias) |

> Dezembro/2026: dias úteis 01, 02, 03, 04, 07 → d5 = 07/12. Novembro/2026: 03, 04, 05, 06, 09 → d5 = 09/11. Transformar esses exemplos em testes unitários.

### 3.8 Mensagens e lembretes (RF-MSG)
- **RF-MSG-01** Tipos: `CONVITE`, `LEMBRETE`, `LEMBRETE_PRAZO`, `CONFIRMACAO`, `VESPERA`, `ALTERACAO`, `CANCELAMENTO`.
- **RF-MSG-02** Lembrete mensal: a cada 30 dias desde o convite/último lembrete, para `CONVIDADO` e `AGUARDANDO_PAGAMENTO`, **enquanto hoje < prazo**.
- **RF-MSG-03** Lembrete de prazo: 3 dias antes do prazo e no dia do prazo.
- **RF-MSG-04** Véspera: lembrete "é amanhã!" para os `CONFIRMADO`.
- **RF-MSG-05** Nenhum lembrete para `RECUSOU`, opt-out, evento cancelado/encerrado ou depois do prazo.
- **RF-MSG-06** Envio apenas entre 9h e 20h (horário de Brasília), com intervalo aleatório entre mensagens (ex.: 8–25 s) para reduzir o risco de banimento.
- **RF-MSG-07** Mensagens com textos variados (2–3 variações por tipo), também para reduzir o risco de banimento.
- **RF-MSG-08** Registrar status de cada mensagem (pendente, enviada, entregue, lida, falha), com até 3 novas tentativas.
- **RF-MSG-10** O CONVITE vai com a arte do evento (RF-EVT-09); as demais mensagens são só texto.
- **RF-MSG-09** Templates editáveis por evento, com variáveis: `{nome}`, `{evento}`, `{data}`, `{local}`, `{valor}`, `{prazo}`, `{link}`.

### 3.9 Lista de presentes (RF-PRE)
- **RF-PRE-01** Cadastrar presentes: nome, descrição, link de loja, imagem, modo (`RESERVA`, `DINHEIRO` ou `AMBOS`), valor de referência.
- **RF-PRE-02** **Reserva:** o convidado reserva o presente, que fica indisponível para os outros. Pode cancelar a reserva.
- **RF-PRE-03** **Dinheiro:** o convidado escolhe um valor livre e paga via PIX (mesmo fluxo, cobrança separada, taxa repassada). Barra de progresso até o valor de referência.
- **RF-PRE-04** O pagamento de presente **não** afeta a confirmação de presença.

### 3.10 Painel do organizador (RF-DSH)
- **RF-DSH-01** Contadores por estado do convidado (incluindo prazo vencido) e total de pessoas (convidados + acompanhantes).
- **RF-DSH-02** Por colaboração: arrecadado × meta, sobra e projeção (confirmados × valor).
- **RF-DSH-03** Lista de convidados com filtros por estado, busca e ações (reenviar convite, baixa manual, remover).
- **RF-DSH-04** Histórico de mensagens e pagamentos por convidado.
- **RF-DSH-05** Lista de presentes com reservas e valores recebidos.

---

## 4. Requisitos não funcionais

- **RNF-01 Stack:** FastAPI (Python 3.12+), PostgreSQL no Supabase (com RLS), Supabase Auth e Storage, Angular (standalone components).
- **RNF-02 Hospedagem:** Angular na Vercel. FastAPI + worker + Evolution API em Docker numa VM grátis (Oracle Cloud Always Free), com Caddy para HTTPS automático (necessário para o webhook do MP).
- **RNF-03 Segurança:** tokens do MP criptografados no banco; token do convidado com ≥ 128 bits aleatórios; assinatura do webhook validada; segredos em variáveis de ambiente.
- **RNF-04 Confiabilidade:** fila de mensagens no próprio Postgres (`SELECT … FOR UPDATE SKIP LOCKED`), com novas tentativas; webhooks idempotentes.
- **RNF-05 Agendamento:** APScheduler no worker (jobs a cada 15 min / diários).
- **RNF-06 Mobile-first:** página do convidado leve, com carregamento rápido em 4G.
- **RNF-07 LGPD:** aviso de privacidade no convite, opt-out, exclusão dos dados do convidado a pedido.
- **RNF-08 Fuso:** tudo em `America/Sao_Paulo` na exibição; `timestamptz` no banco.
- **RNF-09 Testes:** testes unitários obrigatórios para o cálculo de prazo, valores/taxa e máquina de estados.

---

## 5. Modelo de dados

```
organizador 1─1 integracao_mp
organizador 1─1 integracao_whatsapp
organizador 1─N evento
evento 1─N atracao | item_cardapio | colaboracao | presente | convidado
convidado 1─N pagamento | mensagem
convidado 1─N convidado_colaboracao (snapshot do valor)
presente 1─N pagamento (tipo PRESENTE) | reserva via presente.reservado_por
```

### Tabelas

**organizador**: `id (= auth.users.id)`, `nome`, `telefone`, `criado_em`

**integracao_mp**: `organizador_id PK/FK`, `mp_user_id`, `access_token_enc`, `refresh_token_enc`, `public_key`, `expira_em`, `status (ATIVA|EXPIRADA|ERRO)`, `atualizado_em`

**integracao_whatsapp**: `organizador_id PK/FK`, `instancia`, `numero`, `status (CONECTADO|DESCONECTADO|AGUARDANDO_QR)`, `atualizado_em`

**evento**: `id`, `organizador_id FK`, `nome`, `descricao`, `local_nome`, `endereco`, `mapa_url`, `data_hora timestamptz`, `capa_url`, `convite_imagem_url`, `tem_contribuicao bool`, `max_acompanhantes int null`, `prazo_pagamento date`, `prazo_manual bool`, `taxa_mp numeric(5,4) default 0.0099`, `status`, `criado_em`

**atracao**: `id`, `evento_id FK`, `nome`, `descricao`, `horario time null`, `ordem`

**item_cardapio**: `id`, `evento_id FK`, `categoria`, `nome`, `descricao`, `ordem`

**colaboracao**: `id`, `evento_id FK`, `descricao`, `tipo (FIXO|RATEIO)`, `meta numeric(12,2) null`, `valor_por_pessoa numeric(12,2) null`, `pessoas_estimadas int null`, `ordem`
- CHECK: FIXO → `valor_por_pessoa` obrigatório; RATEIO → `meta` e `pessoas_estimadas` obrigatórios

**convidado**: `id`, `evento_id FK`, `nome`, `telefone_e164`, `token unique`, `status`, `qtd_acompanhantes int default 0`, `valor_por_pessoa numeric(12,2)` (soma congelada), `opt_out bool`, `convidado_em`, `respondeu_em`, `confirmado_em`, `ultimo_lembrete_em`
- UNIQUE (`evento_id`, `telefone_e164`)
- Valor devido = `valor_por_pessoa × (1 + qtd_acompanhantes)` (coluna gerada ou view)

**convidado_colaboracao**: `convidado_id FK`, `colaboracao_id FK`, `valor_por_pessoa`: snapshot por colaboração, para o painel de arrecadação por colaboração

**presente**: `id`, `evento_id FK`, `nome`, `descricao`, `link_loja`, `imagem_url`, `modo (RESERVA|DINHEIRO|AMBOS)`, `valor_referencia numeric(12,2) null`, `reservado_por FK convidado null`, `reservado_em`

**pagamento**: `id`, `convidado_id FK`, `tipo (CONTRIBUICAO|PRESENTE)`, `presente_id FK null`, `valor_liquido`, `valor_cobrado`, `origem (MERCADO_PAGO|MANUAL)`, `mp_order_id unique null`, `mp_payment_id unique null`, `pix_copia_cola`, `pix_qr_base64`, `expira_em`, `status (PENDENTE|APROVADO|EXPIRADO|CANCELADO|ESTORNADO)`, `pago_em`, `comprovante_path null`, `observacao`, `criado_em`

**mensagem**: `id`, `convidado_id FK`, `tipo`, `conteudo`, `midia_url`, `status (PENDENTE|ENVIADA|ENTREGUE|LIDA|FALHA)`, `tentativas`, `agendada_para`, `enviada_em`, `id_externo`, `erro`

**webhook_recebido**: `id`, `origem (MP|EVOLUTION)`, `id_externo`, `payload jsonb`, `recebido_em`, `processado_em`, `erro`
- UNIQUE (`origem`, `id_externo`): garante a idempotência

### Máquina de estados do convidado
```
               "Vou" (sem contribuição)
CONVIDADO ───────────────────────────────► CONFIRMADO
   │  "Vou" (com contribuição)                  ▲   │ estorno
   ├──────────────► AGUARDANDO_PAGAMENTO ───────┘   ▼
   │                      ▲  pagamento aprovado /   AGUARDANDO_PAGAMENTO
   │ "Não vou"            │  baixa manual
   ▼                      │ "Vou" novamente
RECUSOU ──────────────────┘
```

---

## 6. Jobs e integrações

| Job | Frequência | O que faz |
|---|---|---|
| `enviar_mensagens` | contínuo (worker) | Consome a fila `mensagem`, respeita a janela 9h–20h e o intervalo aleatório |
| `agendar_lembretes` | diário 9h | Cria mensagens LEMBRETE / LEMBRETE_PRAZO / VESPERA conforme RF-MSG |
| `expirar_cobrancas` | 15 min | Marca PIX vencidos como EXPIRADO |
| `reconciliar_pagamentos` | 1 h | Consulta no MP as cobranças PENDENTES (caso algum webhook se perca) |
| `renovar_tokens_mp` | diário | Renova tokens que vencem em < 15 dias |
| `encerrar_eventos` | diário | Eventos com data passada → ENCERRADO |
| `checar_whatsapp` | 10 min | Atualiza o status das instâncias na Evolution |

| Integração | Uso |
|---|---|
| Mercado Pago Orders API | Criar cobrança PIX, consultar pagamento |
| Mercado Pago OAuth | Conectar a conta do organizador, renovar o token |
| Mercado Pago Webhook | `POST /webhooks/mercadopago` |
| Evolution API | Criar instância/QR, enviar texto, webhook de status (`POST /webhooks/evolution`) |
| Supabase | Postgres, Auth (organizador), Storage (capas, imagens, comprovantes) |

---

## 7. Telas

### Organizador (autenticado)
1. **Login / cadastro**
2. **Configurações**: conectar Mercado Pago (botão OAuth), conectar WhatsApp (QR Code + status), dados do perfil
3. **Meus eventos**: cards com data, status, confirmados/total, arrecadado
4. **Evento — edição** (abas): Dados · Atrações · Cardápio · Colaborações · Presentes · Mensagens (templates) · Prazo
5. **Evento — convidados**: tabela com estado, valor, ações; adicionar; importar CSV
6. **Evento — painel**: contadores, arrecadação por colaboração, presentes, alertas (WhatsApp desconectado, falhas de envio)
7. **Convidado — detalhe** (drawer): histórico de mensagens e pagamentos, baixa manual

### Convidado (link público `/{token}`)
1. **Convite / evento**: todas as informações do evento + estado atual do convidado
2. **Confirmação**: nome, acompanhantes, "Vou" / "Não vou", valor total
3. **Pagamento**: QR Code, copia-e-cola, valor, prazo, status ao vivo
4. **Presentes**: reservar ou contribuir
5. **Confirmado**: tela de sucesso + "adicionar à agenda" (.ics)

---

## 8. Exemplos de mensagens

**Convite**
> Oi, {nome}! 🎉 Você está convidado(a) para **{evento}**, dia {data} em {local}.
> Confirma sua presença por aqui: {link}

**Lembrete**
> Oi, {nome}! Passando para lembrar do **{evento}** ({data}). Sua contribuição de {valor} ainda está pendente, e dá para pagar até {prazo}: {link}

**Confirmação**
> Presença confirmada, {nome}! ✅ Te esperamos no **{evento}**, dia {data}. Detalhes: {link}

**Véspera**
> É amanhã! 🎈 **{evento}**, {data} em {local}. Até lá!

---

## 9. Roadmap

**MVP**
1. Setup: repositórios, Supabase (schema + RLS), FastAPI, Angular, VM com Docker (Evolution + backend + Caddy)
2. Auth do organizador + CRUD de evento (dados, colaborações)
3. Convidados + token + página pública do convidado (confirmação/acompanhantes)
4. WhatsApp: conexão via QR + fila de envio + convite
5. Mercado Pago: OAuth + PIX + webhook + reconciliação
6. Prazo + lembretes + véspera
7. Painel do organizador

**Fase 2**
- Lista de presentes (reserva + dinheiro)
- Atrações e cardápio na página pública
- Importação CSV, templates editáveis, .ics
- Baixa manual com comprovante

**Pontos a validar antes de codar**
- Taxa real do PIX via API na conta MP pessoa física (o site informa 0,99%)
- Se a conta MP pessoa física permite criar aplicação com OAuth em produção
- Limites de envio do WhatsApp não oficial (testar com poucos convidados primeiro)
