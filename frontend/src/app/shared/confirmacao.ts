import { Component, effect, ElementRef, HostListener, inject, Injectable, signal, viewChild } from '@angular/core';

export interface PedidoConfirmacao {
  titulo: string;
  mensagem?: string;
  /** Texto do botão que faz a ação (ex.: "Cancelar evento"). Nunca "OK". */
  confirmar: string;
  /** Texto do botão que desiste. Padrão: "Voltar". */
  voltar?: string;
  /** Ação que apaga ou desfaz algo: botão em vermelho. */
  perigo?: boolean;
}

/**
 * Confirmação no visual do Bora, no lugar do confirm() do navegador.
 *
 *   if (!(await this.confirmacao.pedir({ titulo: 'Remover Ana?', confirmar: 'Remover', perigo: true }))) return;
 */
@Injectable({ providedIn: 'root' })
export class ConfirmacaoService {
  readonly atual = signal<PedidoConfirmacao | null>(null);
  private responder?: (sim: boolean) => void;

  pedir(pedido: PedidoConfirmacao): Promise<boolean> {
    this.responder?.(false); // um pedido por vez: o anterior conta como "voltar"
    this.atual.set(pedido);
    return new Promise((resolve) => (this.responder = resolve));
  }

  fechar(sim: boolean) {
    this.atual.set(null);
    const r = this.responder;
    this.responder = undefined;
    r?.(sim);
  }
}

/** Fica uma vez na raiz do app (app.html). */
@Component({
  selector: 'bora-confirmacao',
  template: `
    @if (servico.atual(); as p) {
      <div class="fundo" (click)="servico.fechar(false)">
        <div
          class="folha"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="confirmacao-titulo"
          [attr.aria-describedby]="p.mensagem ? 'confirmacao-mensagem' : null"
          (click)="$event.stopPropagation()"
        >
          <h2 id="confirmacao-titulo">{{ p.titulo }}</h2>
          @if (p.mensagem) {
            <p id="confirmacao-mensagem">{{ p.mensagem }}</p>
          }
          <div class="botoes">
            <button #voltar type="button" class="botao-secundario" (click)="servico.fechar(false)">
              {{ p.voltar ?? 'Voltar' }}
            </button>
            <button type="button" [class.perigo]="p.perigo" (click)="servico.fechar(true)">
              {{ p.confirmar }}
            </button>
          </div>
        </div>
      </div>
    }
  `,
  styles: `
    .fundo {
      position: fixed;
      inset: 0;
      z-index: 100;
      display: grid;
      place-items: end center;
      padding: 16px;
      padding-bottom: calc(16px + env(safe-area-inset-bottom));
      background: rgb(0 0 0 / 40%);
      animation: aparece 0.2s ease;

      @media (min-width: 640px) {
        place-items: center;
      }
    }

    .folha {
      width: min(400px, 100%);
      padding: 24px;
      border-radius: var(--raio-midia);
      background: var(--superficie);
      box-shadow: var(--sombra-elevada);
      display: flex;
      flex-direction: column;
      gap: 8px;
      animation: sobe 0.35s cubic-bezier(0.16, 1, 0.3, 1);
    }

    h2 {
      font-size: 1.35rem;
      line-height: 1.2;
    }

    p {
      color: var(--tinta-2);
      line-height: 1.45;
    }

    .botoes {
      margin-top: 14px;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;

      button {
        min-height: 50px;
      }
    }

    /* vermelho com contraste suficiente para o texto nos dois temas */
    .perigo {
      background: color-mix(in srgb, var(--erro) 86%, #000);
      color: #fff;

      &:hover {
        background: color-mix(in srgb, var(--erro) 76%, #000);
      }

      @media (prefers-color-scheme: dark) {
        background: var(--erro);
        color: #2b0b0c;

        &:hover {
          background: color-mix(in srgb, var(--erro) 88%, #fff);
        }
      }
    }

    @keyframes aparece {
      from {
        opacity: 0;
      }
    }

    @keyframes sobe {
      from {
        transform: translateY(32px);
        opacity: 0;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      .fundo,
      .folha {
        animation: none;
      }
    }
  `,
})
export class Confirmacao {
  readonly servico = inject(ConfirmacaoService);
  private readonly voltar = viewChild<ElementRef<HTMLButtonElement>>('voltar');

  constructor() {
    // Foco no "Voltar" quando abre: um Enter sem querer não executa a ação
    // (sem o contorno de foco: ele aparece só quando a pessoa usa o teclado)
    effect(() => this.voltar()?.nativeElement.focus({ focusVisible: false } as FocusOptions));
  }

  @HostListener('document:keydown.escape')
  esc() {
    if (this.servico.atual()) this.servico.fechar(false);
  }
}
