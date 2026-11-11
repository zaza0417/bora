import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { SupabaseService } from '../../core/supabase.service';
import { Logo } from '../../shared/logo';

/** Página de apresentação: o que o Bora faz, contado pelo próprio convite. */
@Component({
  selector: 'app-inicio',
  imports: [RouterLink, Logo],
  templateUrl: './inicio.html',
  styleUrl: './inicio.scss',
})
export class Inicio {
  readonly logado = inject(SupabaseService).session;

  readonly passos = [
    {
      titulo: 'Crie o evento',
      texto: 'Data, local, a arte do convite e quanto cada um ajuda. Leva dois minutos.',
    },
    {
      titulo: 'O convite chega no WhatsApp',
      texto: 'Sai do seu número, com a arte e o link de cada convidado.',
    },
    {
      titulo: 'Cada um responde pelo link',
      texto: 'Diz se vai, quantos leva e paga o PIX com o valor já certinho.',
    },
    {
      titulo: 'O comprovante confirma a presença',
      texto: 'O Bora lê o comprovante que chega no seu WhatsApp e confere valor, data e nome.',
    },
  ];
}
