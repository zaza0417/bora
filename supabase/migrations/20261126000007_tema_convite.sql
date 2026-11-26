-- Tema visual do convite (cor, tipografia e tom do texto da página do convidado e da
-- prévia do link no WhatsApp). Eventos antigos ficam com o visual de sempre (FESTA).
alter table evento
  add column tema text not null default 'FESTA',
  add constraint ck_evento_tema check (tema in ('FESTA', 'NOITE', 'CASAMENTO', 'INFANTIL'));
