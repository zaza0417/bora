-- =====================================================================
-- PIX manual: chave do organizador + comprovante recebido pelo WhatsApp
-- (alternativa ao Mercado Pago; ver docs/requisitos.md §3.6)
-- =====================================================================

alter table organizador
  add column pix_chave  text,          -- CPF, e-mail, telefone ou chave aleatória
  add column pix_nome   text,          -- nome do recebedor (aparece no app do banco)
  add column pix_cidade text;          -- cidade do recebedor (exigida pelo BR Code)

alter table convidado
  add column comprovante_path          text,         -- bucket privado "comprovantes"
  add column comprovante_recebido_em   timestamptz,
  add column comprovante_mensagem_id   text;         -- id da mensagem no WhatsApp (dedupe)

create index idx_convidado_comprovante_pendente
  on convidado (evento_id)
  where comprovante_recebido_em is not null and status <> 'CONFIRMADO';

-- Resposta automática quando o comprovante chega
alter type tipo_mensagem add value if not exists 'COMPROVANTE_RECEBIDO';
