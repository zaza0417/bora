import { Component, input } from '@angular/core';

/**
 * Marca do Bora: um "b" que também é um balão de conversa — a haste vira o rabinho
 * do balão (convite que chega pelo WhatsApp). Ícone no formato de app, amarelo festa
 * chapado com o glifo em tinta; ao lado, o nome em Bricolage Grotesque.
 */
@Component({
  selector: 'bora-logo',
  template: `
    <span class="logo" [class.so-marca]="soMarca()" [style.--tam.px]="tamanho()">
      <svg class="marca" viewBox="0 0 64 64" aria-hidden="true">
        <rect width="64" height="64" rx="15" fill="#FFD23F" />
        <path
          fill="#1D1D1F"
          fill-rule="evenodd"
          d="M20 10a4 4 0 0 1 8 0v14.6A16.5 16.5 0 1 1 35.6 52.4H22.5l-7.7 5.2a1.4 1.4 0 0 1-2.1-1.6L16 48.6A6 6 0 0 1 20 43ZM28 35.5a7.6 7.6 0 1 0 7.6-7.6 7.6 7.6 0 0 0-7.6 7.6Z"
        />
      </svg>
      @if (!soMarca()) {
        <span class="nome">bora</span>
      }
      <span class="sr-only">Bora</span>
    </span>
  `,
  styles: `
    .logo {
      --tam: 32px;
      display: inline-flex;
      align-items: center;
      gap: calc(var(--tam) * 0.28);
      color: var(--tinta);
      text-decoration: none;
    }
    .marca {
      width: var(--tam);
      height: var(--tam);
      flex: none;
      box-shadow: inset 0 0 0 0.5px rgb(0 0 0 / 0.06);
      border-radius: 23%;
    }
    .nome {
      font-family: var(--fonte-display);
      font-weight: 800;
      font-size: calc(var(--tam) * 0.92);
      letter-spacing: -0.05em;
      line-height: 1;
      transform: translateY(-0.04em);
    }
  `,
})
export class Logo {
  readonly tamanho = input(32);
  readonly soMarca = input(false);
}
