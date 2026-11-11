import { Component, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { SupabaseService } from '../core/supabase.service';
import { Logo } from './logo';

/** Barra do organizador: translúcida, fixa no topo, como a navegação do site da Apple. */
@Component({
  selector: 'bora-topo',
  imports: [RouterLink, RouterLinkActive, Logo],
  template: `
    <header class="topo">
      <nav class="dentro" aria-label="Principal">
        <a routerLink="/eventos" class="inicio" aria-label="Bora, meus eventos">
          <bora-logo [tamanho]="26" />
        </a>
        <div class="links">
          <a routerLink="/eventos" routerLinkActive="ativo" [routerLinkActiveOptions]="{ exact: true }">Eventos</a>
          <a routerLink="/configuracoes" routerLinkActive="ativo">Ajustes</a>
          <button type="button" class="sair" (click)="sair()">Sair</button>
        </div>
      </nav>
    </header>
  `,
  styles: `
    .topo {
      position: sticky;
      top: 0;
      z-index: 20;
      background: color-mix(in srgb, var(--fundo) 78%, transparent);
      backdrop-filter: saturate(180%) blur(20px);
      -webkit-backdrop-filter: saturate(180%) blur(20px);
      border-bottom: 0.5px solid var(--linha);
    }
    .dentro {
      max-width: var(--largura);
      margin: 0 auto;
      height: 52px;
      padding: 0 22px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .inicio:hover {
      text-decoration: none;
    }
    .links {
      display: flex;
      align-items: center;
      gap: 22px;
      font-size: 0.88rem;
    }
    .links a {
      color: var(--tinta-2);
    }
    .links a.ativo,
    .links a:hover {
      color: var(--tinta);
      text-decoration: none;
    }
    .sair {
      min-height: 0;
      padding: 0;
      background: none;
      color: var(--tinta-2);
      font-size: 0.88rem;
    }
    .sair:hover {
      background: none;
      color: var(--tinta);
    }
  `,
})
export class Topo {
  private readonly supabase = inject(SupabaseService);
  private readonly router = inject(Router);

  async sair() {
    await this.supabase.sair();
    await this.router.navigateByUrl('/');
  }
}
