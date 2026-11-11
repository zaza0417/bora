-- =====================================================================
-- Row Level Security
--
-- Modelo de acesso:
--  * Organizador (role "authenticated"): lê/escreve só os próprios eventos e filhos.
--  * Convidado: NÃO acessa o banco diretamente — passa pelo backend (FastAPI),
--    que usa a service role (ignora RLS) e valida o token do link.
--  * Tokens de integração (integracao_mp): sem policy → só o backend acessa.
-- =====================================================================

alter table organizador           enable row level security;
alter table integracao_mp         enable row level security;
alter table integracao_whatsapp   enable row level security;
alter table evento                enable row level security;
alter table atracao               enable row level security;
alter table item_cardapio         enable row level security;
alter table colaboracao           enable row level security;
alter table convidado             enable row level security;
alter table convidado_colaboracao enable row level security;
alter table presente              enable row level security;
alter table pagamento             enable row level security;
alter table mensagem              enable row level security;
alter table webhook_recebido      enable row level security;

-- Helper: o evento pertence ao usuário logado?
create or replace function eh_dono_evento(p_evento_id uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from evento e where e.id = p_evento_id and e.organizador_id = auth.uid());
$$;

create or replace function eh_dono_convidado(p_convidado_id uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from convidado c join evento e on e.id = c.evento_id
    where c.id = p_convidado_id and e.organizador_id = auth.uid()
  );
$$;

-- Organizador: só o próprio registro
create policy organizador_self on organizador
  for all to authenticated
  using (id = auth.uid()) with check (id = auth.uid());

-- WhatsApp: organizador pode ver o status da própria instância (escrita só pelo backend)
create policy whatsapp_select_own on integracao_whatsapp
  for select to authenticated using (organizador_id = auth.uid());

-- integracao_mp: nenhuma policy de propósito (tokens). O backend expõe só o status.

-- Evento
create policy evento_owner on evento
  for all to authenticated
  using (organizador_id = auth.uid()) with check (organizador_id = auth.uid());

-- Filhos diretos do evento
create policy atracao_owner on atracao
  for all to authenticated using (eh_dono_evento(evento_id)) with check (eh_dono_evento(evento_id));
create policy item_cardapio_owner on item_cardapio
  for all to authenticated using (eh_dono_evento(evento_id)) with check (eh_dono_evento(evento_id));
create policy colaboracao_owner on colaboracao
  for all to authenticated using (eh_dono_evento(evento_id)) with check (eh_dono_evento(evento_id));
create policy presente_owner on presente
  for all to authenticated using (eh_dono_evento(evento_id)) with check (eh_dono_evento(evento_id));

-- Convidados: leitura direta liberada ao dono; criação/alteração passa pelo backend
-- (gera token, snapshot de valores e enfileira o convite).
create policy convidado_select_owner on convidado
  for select to authenticated using (eh_dono_evento(evento_id));

create policy convidado_colaboracao_select_owner on convidado_colaboracao
  for select to authenticated using (eh_dono_convidado(convidado_id));

-- Pagamentos e mensagens: somente leitura para o dono
create policy pagamento_select_owner on pagamento
  for select to authenticated using (eh_dono_convidado(convidado_id));
create policy mensagem_select_owner on mensagem
  for select to authenticated using (eh_dono_convidado(convidado_id));

-- webhook_recebido: nenhuma policy (somente backend).

-- ---------------------------------------------------------------------
-- Storage: buckets
--  * capas      → público (imagens de capa e presentes)
--  * comprovantes → privado (somente backend / signed URLs)
-- ---------------------------------------------------------------------
insert into storage.buckets (id, name, public) values
  ('capas', 'capas', true),
  ('comprovantes', 'comprovantes', false)
on conflict (id) do nothing;

-- Organizador pode subir arquivos em capas/<seu uid>/...
create policy capas_upload_own on storage.objects
  for insert to authenticated
  with check (bucket_id = 'capas' and (storage.foldername(name))[1] = auth.uid()::text);
create policy capas_update_own on storage.objects
  for update to authenticated
  using (bucket_id = 'capas' and (storage.foldername(name))[1] = auth.uid()::text);
create policy capas_delete_own on storage.objects
  for delete to authenticated
  using (bucket_id = 'capas' and (storage.foldername(name))[1] = auth.uid()::text);
