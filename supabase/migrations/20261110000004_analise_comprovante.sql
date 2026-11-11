-- =====================================================================
-- Conferência automática do comprovante (OCR) + baixa automática opcional
-- =====================================================================

alter table convidado
  add column comprovante_analise jsonb,   -- resultado de app/domain/comprovante.py
  add column comprovante_e2e     text;    -- ID da transação PIX lido no comprovante

-- Mesmo comprovante não pode valer para dois convidados
create unique index uq_convidado_comprovante_e2e
  on convidado (comprovante_e2e) where comprovante_e2e is not null;

alter table organizador
  add column baixa_automatica boolean not null default false;  -- confirmar quando tudo confere
