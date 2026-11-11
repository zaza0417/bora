-- =====================================================================
-- Plataforma de Eventos — schema inicial
-- Ver docs/requisitos.md, seção 5 (Modelo de dados)
-- =====================================================================

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------
-- Tipos
-- ---------------------------------------------------------------------
create type status_evento        as enum ('RASCUNHO', 'ATIVO', 'ENCERRADO', 'CANCELADO');
create type tipo_colaboracao     as enum ('FIXO', 'RATEIO');
create type status_convidado     as enum ('CONVIDADO', 'AGUARDANDO_PAGAMENTO', 'CONFIRMADO', 'RECUSOU');
create type modo_presente        as enum ('RESERVA', 'DINHEIRO', 'AMBOS');
create type tipo_pagamento       as enum ('CONTRIBUICAO', 'PRESENTE');
create type origem_pagamento     as enum ('MERCADO_PAGO', 'MANUAL');
create type status_pagamento     as enum ('PENDENTE', 'APROVADO', 'EXPIRADO', 'CANCELADO', 'ESTORNADO');
create type tipo_mensagem        as enum ('CONVITE', 'LEMBRETE', 'LEMBRETE_PRAZO', 'CONFIRMACAO', 'VESPERA', 'ALTERACAO', 'CANCELAMENTO');
create type status_mensagem      as enum ('PENDENTE', 'ENVIADA', 'ENTREGUE', 'LIDA', 'FALHA');
create type status_integracao_mp as enum ('ATIVA', 'EXPIRADA', 'ERRO');
create type status_whatsapp      as enum ('CONECTADO', 'DESCONECTADO', 'AGUARDANDO_QR');
create type origem_webhook       as enum ('MP', 'EVOLUTION');

-- ---------------------------------------------------------------------
-- Função utilitária: atualizado_em automático
-- ---------------------------------------------------------------------
create or replace function set_atualizado_em() returns trigger
language plpgsql as $$
begin
  new.atualizado_em := now();
  return new;
end $$;

-- ---------------------------------------------------------------------
-- Organizador (1:1 com auth.users)
-- ---------------------------------------------------------------------
create table organizador (
  id         uuid primary key references auth.users (id) on delete cascade,
  nome       text not null,
  telefone   text,
  criado_em  timestamptz not null default now()
);

-- Cria o organizador automaticamente quando um usuário se cadastra no Supabase Auth
create or replace function criar_organizador_para_usuario() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.organizador (id, nome)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'nome', split_part(new.email, '@', 1)));
  return new;
end $$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function criar_organizador_para_usuario();

-- ---------------------------------------------------------------------
-- Integrações do organizador (tokens só acessíveis pelo backend)
-- ---------------------------------------------------------------------
create table integracao_mp (
  organizador_id     uuid primary key references organizador (id) on delete cascade,
  mp_user_id         text not null,
  access_token_enc   text not null,
  refresh_token_enc  text not null,
  public_key         text,
  expira_em          timestamptz not null,
  status             status_integracao_mp not null default 'ATIVA',
  atualizado_em      timestamptz not null default now()
);
create trigger trg_integracao_mp_upd before update on integracao_mp
  for each row execute function set_atualizado_em();

create table integracao_whatsapp (
  organizador_id  uuid primary key references organizador (id) on delete cascade,
  instancia       text not null unique,
  numero          text,
  status          status_whatsapp not null default 'AGUARDANDO_QR',
  atualizado_em   timestamptz not null default now()
);
create trigger trg_integracao_whatsapp_upd before update on integracao_whatsapp
  for each row execute function set_atualizado_em();

-- ---------------------------------------------------------------------
-- Evento
-- ---------------------------------------------------------------------
create table evento (
  id                 uuid primary key default gen_random_uuid(),
  organizador_id     uuid not null references organizador (id) on delete cascade,
  nome               text not null,
  descricao          text,
  local_nome         text,
  endereco           text,
  mapa_url           text,
  data_hora          timestamptz not null,
  capa_url           text,
  convite_imagem_url text,  -- arte do convite enviada no WhatsApp (bucket 'capas')
  tem_contribuicao   boolean not null default false,
  max_acompanhantes  int check (max_acompanhantes is null or max_acompanhantes >= 0),
  prazo_pagamento    date,
  prazo_manual       boolean not null default false,
  taxa_mp            numeric(5,4) not null default 0.0099 check (taxa_mp >= 0 and taxa_mp < 1),
  status             status_evento not null default 'RASCUNHO',
  criado_em          timestamptz not null default now(),
  atualizado_em      timestamptz not null default now()
);
create index idx_evento_organizador on evento (organizador_id);
create index idx_evento_status_data on evento (status, data_hora);
create trigger trg_evento_upd before update on evento
  for each row execute function set_atualizado_em();

create table atracao (
  id         uuid primary key default gen_random_uuid(),
  evento_id  uuid not null references evento (id) on delete cascade,
  nome       text not null,
  descricao  text,
  horario    time,
  ordem      int not null default 0
);
create index idx_atracao_evento on atracao (evento_id);

create table item_cardapio (
  id         uuid primary key default gen_random_uuid(),
  evento_id  uuid not null references evento (id) on delete cascade,
  categoria  text,
  nome       text not null,
  descricao  text,
  ordem      int not null default 0
);
create index idx_item_cardapio_evento on item_cardapio (evento_id);

-- ---------------------------------------------------------------------
-- Colaborações
-- ---------------------------------------------------------------------
create table colaboracao (
  id                 uuid primary key default gen_random_uuid(),
  evento_id          uuid not null references evento (id) on delete cascade,
  descricao          text not null,
  tipo               tipo_colaboracao not null,
  meta               numeric(12,2) check (meta is null or meta > 0),
  valor_por_pessoa   numeric(12,2) check (valor_por_pessoa is null or valor_por_pessoa > 0),
  pessoas_estimadas  int check (pessoas_estimadas is null or pessoas_estimadas > 0),
  ordem              int not null default 0,
  constraint ck_colaboracao_tipo check (
    (tipo = 'FIXO'   and valor_por_pessoa is not null) or
    (tipo = 'RATEIO' and meta is not null and pessoas_estimadas is not null)
  )
);
create index idx_colaboracao_evento on colaboracao (evento_id);

-- ---------------------------------------------------------------------
-- Convidados
-- ---------------------------------------------------------------------
create table convidado (
  id                  uuid primary key default gen_random_uuid(),
  evento_id           uuid not null references evento (id) on delete cascade,
  nome                text not null,
  telefone_e164       text not null check (telefone_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  token               text not null unique,
  status              status_convidado not null default 'CONVIDADO',
  qtd_acompanhantes   int not null default 0 check (qtd_acompanhantes >= 0),
  -- soma congelada (snapshot) do valor por pessoa de todas as colaborações no envio do convite
  valor_por_pessoa    numeric(12,2) not null default 0,
  valor_devido        numeric(12,2) generated always as (valor_por_pessoa * (1 + qtd_acompanhantes)) stored,
  opt_out             boolean not null default false,
  convidado_em        timestamptz not null default now(),
  respondeu_em        timestamptz,
  confirmado_em       timestamptz,
  ultimo_lembrete_em  timestamptz,
  constraint uq_convidado_evento_telefone unique (evento_id, telefone_e164)
);
create index idx_convidado_evento_status on convidado (evento_id, status);

-- Snapshot do valor por colaboração (para o painel de arrecadação por colaboração)
create table convidado_colaboracao (
  convidado_id      uuid not null references convidado (id) on delete cascade,
  colaboracao_id    uuid not null references colaboracao (id) on delete cascade,
  valor_por_pessoa  numeric(12,2) not null,
  primary key (convidado_id, colaboracao_id)
);

-- ---------------------------------------------------------------------
-- Presentes
-- ---------------------------------------------------------------------
create table presente (
  id                uuid primary key default gen_random_uuid(),
  evento_id         uuid not null references evento (id) on delete cascade,
  nome              text not null,
  descricao         text,
  link_loja         text,
  imagem_url        text,
  modo              modo_presente not null default 'RESERVA',
  valor_referencia  numeric(12,2) check (valor_referencia is null or valor_referencia > 0),
  reservado_por     uuid references convidado (id) on delete set null,
  reservado_em      timestamptz,
  ordem             int not null default 0
);
create index idx_presente_evento on presente (evento_id);

-- ---------------------------------------------------------------------
-- Pagamentos
-- ---------------------------------------------------------------------
create table pagamento (
  id               uuid primary key default gen_random_uuid(),
  convidado_id     uuid not null references convidado (id) on delete cascade,
  tipo             tipo_pagamento not null default 'CONTRIBUICAO',
  presente_id      uuid references presente (id) on delete set null,
  valor_liquido    numeric(12,2) not null check (valor_liquido > 0),
  valor_cobrado    numeric(12,2) not null check (valor_cobrado >= valor_liquido),
  origem           origem_pagamento not null default 'MERCADO_PAGO',
  mp_order_id      text unique,
  mp_payment_id    text unique,
  pix_copia_cola   text,
  pix_qr_base64    text,
  expira_em        timestamptz,
  status           status_pagamento not null default 'PENDENTE',
  pago_em          timestamptz,
  comprovante_path text,
  observacao       text,
  criado_em        timestamptz not null default now(),
  constraint ck_pagamento_presente check ((tipo = 'PRESENTE') = (presente_id is not null))
);
create index idx_pagamento_convidado on pagamento (convidado_id);
create index idx_pagamento_pendente on pagamento (status, expira_em) where status = 'PENDENTE';
-- RF-PGT-09: no máximo uma cobrança pendente de contribuição por convidado
create unique index uq_pagamento_contribuicao_pendente
  on pagamento (convidado_id) where status = 'PENDENTE' and tipo = 'CONTRIBUICAO';

-- ---------------------------------------------------------------------
-- Mensagens (também funciona como fila de envio)
-- ---------------------------------------------------------------------
create table mensagem (
  id             uuid primary key default gen_random_uuid(),
  convidado_id   uuid not null references convidado (id) on delete cascade,
  tipo           tipo_mensagem not null,
  conteudo       text not null,
  midia_url      text,  -- imagem enviada junto (texto vira legenda)
  status         status_mensagem not null default 'PENDENTE',
  tentativas     int not null default 0,
  agendada_para  timestamptz not null default now(),
  enviada_em     timestamptz,
  id_externo     text,
  erro           text,
  criado_em      timestamptz not null default now()
);
create index idx_mensagem_fila on mensagem (agendada_para) where status = 'PENDENTE';
create index idx_mensagem_convidado on mensagem (convidado_id);
create index idx_mensagem_id_externo on mensagem (id_externo) where id_externo is not null;

-- ---------------------------------------------------------------------
-- Webhooks recebidos (idempotência + auditoria)
-- ---------------------------------------------------------------------
create table webhook_recebido (
  id             uuid primary key default gen_random_uuid(),
  origem         origem_webhook not null,
  id_externo     text not null,
  payload        jsonb not null,
  recebido_em    timestamptz not null default now(),
  processado_em  timestamptz,
  erro           text,
  constraint uq_webhook_origem_id unique (origem, id_externo)
);

-- ---------------------------------------------------------------------
-- View: arrecadação por colaboração (para o painel)
-- ---------------------------------------------------------------------
create view vw_arrecadacao_colaboracao with (security_invoker = true) as
select
  col.id                                   as colaboracao_id,
  col.evento_id,
  col.descricao,
  col.tipo,
  col.meta,
  coalesce(sum(cc.valor_por_pessoa * (1 + cv.qtd_acompanhantes))
           filter (where cv.status = 'CONFIRMADO'), 0)       as arrecadado,
  coalesce(sum(cc.valor_por_pessoa * (1 + cv.qtd_acompanhantes))
           filter (where cv.status in ('CONFIRMADO', 'AGUARDANDO_PAGAMENTO')), 0) as projetado
from colaboracao col
left join convidado_colaboracao cc on cc.colaboracao_id = col.id
left join convidado cv              on cv.id = cc.convidado_id
group by col.id;
