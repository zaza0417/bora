-- Fase 2: textos das mensagens por evento (RF-MSG-09) e lista de presentes (RF-PRE).
-- A tabela `presente` e o tipo de pagamento PRESENTE já existem desde a 0001.

-- Textos personalizados: {"CONVITE": "Oi, {nome}! ...", ...}. Tipo ausente = texto padrão.
alter table evento
  add column mensagens jsonb not null default '{}'::jsonb,
  add constraint ck_evento_mensagens check (jsonb_typeof(mensagens) = 'object');

-- Presente em dinheiro no PIX do organizador: o convidado avisa "já paguei" (PENDENTE)
-- e o organizador confere no extrato (APROVADO) ou descarta (CANCELADO).
create index idx_pagamento_presente on pagamento (presente_id) where presente_id is not null;

-- Presente com reserva ou dinheiro registrado não pode ser apagado: o ON DELETE SET NULL
-- do pagamento esbarraria em ck_pagamento_presente. O erro fica explícito aqui.
create or replace function privado.bloquear_remocao_presente() returns trigger
language plpgsql set search_path = '' as $$
begin
  -- Apagando o evento inteiro (cascata): o evento já sumiu, deixa passar.
  if not exists (select 1 from public.evento e where e.id = old.evento_id) then
    return old;
  end if;
  if old.reservado_por is not null
     or exists (select 1 from public.pagamento p
                 where p.presente_id = old.id and p.status in ('PENDENTE', 'APROVADO')) then
    raise exception 'Presente já foi escolhido por um convidado e não pode ser removido'
      using errcode = 'P0001';
  end if;
  return old;
end $$;

create trigger trg_presente_remocao before delete on presente
  for each row execute function privado.bloquear_remocao_presente();
