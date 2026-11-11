-- =====================================================================
-- Ajustes apontados pela checagem de segurança do Supabase (advisors)
-- =====================================================================

-- 1) Helpers das policies saem do schema public (exposto em /rest/v1/rpc).
--    As policies guardam a referência pela função em si, não pelo nome,
--    então continuam funcionando depois do "set schema".
create schema if not exists privado;
revoke all on schema privado from public;
grant usage on schema privado to authenticated;

alter function public.eh_dono_evento(uuid)    set schema privado;
alter function public.eh_dono_convidado(uuid) set schema privado;

revoke execute on function privado.eh_dono_evento(uuid)    from public, anon;
revoke execute on function privado.eh_dono_convidado(uuid) from public, anon;
grant  execute on function privado.eh_dono_evento(uuid)    to authenticated;
grant  execute on function privado.eh_dono_convidado(uuid) to authenticated;

-- 2) Função do gatilho de cadastro: só o próprio gatilho a usa.
--    (Gatilhos não checam permissão de EXECUTE ao disparar.)
revoke execute on function public.criar_organizador_para_usuario() from public, anon, authenticated;

-- 3) search_path fixo na função de "atualizado_em".
alter function public.set_atualizado_em() set search_path = '';

-- 4) auth.uid() avaliado uma vez por consulta, não uma vez por linha.
alter policy organizador_self on organizador
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

alter policy whatsapp_select_own on integracao_whatsapp
  using (organizador_id = (select auth.uid()));

alter policy evento_owner on evento
  using (organizador_id = (select auth.uid())) with check (organizador_id = (select auth.uid()));
