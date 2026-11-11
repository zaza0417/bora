import { DatePipe } from '@angular/common';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { EventosService } from '../../core/eventos.service';
import { Topo } from '../../shared/topo';

interface EventoResumo {
  id: string;
  nome: string;
  data_hora: string;
  status: string;
  local_nome: string | null;
  convite_imagem_url: string | null;
}

const ROTULO: Record<string, string> = {
  RASCUNHO: 'Rascunho',
  ATIVO: 'Convites enviados',
  ENCERRADO: 'Já aconteceu',
  CANCELADO: 'Cancelado',
};

/** Lista de eventos do organizador: o próximo em destaque, os outros em grade. */
@Component({
  selector: 'app-eventos',
  imports: [DatePipe, RouterLink, Topo],
  template: `
    <bora-topo />
    <main class="pagina">
      <header class="cabeca">
        <h1>Seus eventos</h1>
        <a class="botao" routerLink="/eventos/novo">Novo evento</a>
      </header>

      @if (carregando()) {
        <p class="sub">Carregando seus eventos…</p>
      } @else if (eventos().length === 0) {
        <section class="vazio">
          <h2>Sua primeira festa começa aqui.</h2>
          <p class="sub">Crie o evento, adicione os convidados e o convite sai pelo seu WhatsApp.</p>
          <a class="botao botao-grande" routerLink="/eventos/novo">Criar evento</a>
        </section>
      } @else {
        @if (proximo(); as p) {
          <a class="proximo" [routerLink]="['/eventos', p.id]" [class.com-arte]="p.convite_imagem_url">
            @if (p.convite_imagem_url) {
              <img [src]="p.convite_imagem_url" alt="" />
            }
            <div class="proximo-texto">
              <span class="etiqueta" [class.ok]="p.status === 'ATIVO'">{{ rotulo(p.status) }}</span>
              <h2>{{ p.nome }}</h2>
              <p>
                {{ p.data_hora | date: "EEEE, d 'de' MMMM 'às' HH:mm" }}@if (p.local_nome) {, {{ p.local_nome }} }
              </p>
            </div>
          </a>
        }

        @if (outros().length) {
          <h2 class="titulo-lista">Outros eventos</h2>
          <ul class="grade">
            @for (ev of outros(); track ev.id) {
              <li>
                <a [routerLink]="['/eventos', ev.id]">
                  <span class="data">
                    <strong>{{ ev.data_hora | date: 'd' }}</strong>
                    {{ ev.data_hora | date: 'MMM' }}
                  </span>
                  <span class="info">
                    <strong>{{ ev.nome }}</strong>
                    <span class="sub">{{ rotulo(ev.status) }}</span>
                  </span>
                </a>
              </li>
            }
          </ul>
        }
      }
    </main>
  `,
  styles: `
    .cabeca {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 16px;
      padding: 48px 0 28px;
    }
    .proximo {
      position: relative;
      display: flex;
      align-items: flex-end;
      min-height: 340px;
      border-radius: var(--raio-midia);
      overflow: hidden;
      background: var(--marca);
      color: var(--sobre-marca);
      transition: transform 0.25s ease;
    }
    .proximo:hover {
      text-decoration: none;
      transform: scale(1.005);
    }
    .proximo.com-arte {
      color: #fff;
    }
    .proximo.com-arte::after {
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(to top, rgb(0 0 0 / 70%), transparent 65%);
    }
    .proximo img {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .proximo-texto {
      position: relative;
      z-index: 1;
      padding: 32px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .proximo h2 {
      font-size: clamp(2.4rem, 5vw, 4rem);
      font-weight: 800;
      letter-spacing: -0.05em;
      line-height: 0.95;
    }
    .proximo p::first-letter {
      text-transform: uppercase;
    }
    .proximo .etiqueta {
      align-self: flex-start;
      background: rgb(255 255 255 / 85%);
      color: #1d1d1f;
    }
    .titulo-lista {
      font-size: 1.4rem;
      margin: 48px 0 14px;
    }
    .grade {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 12px;
    }
    .grade a {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 16px;
      border-radius: var(--raio-grupo);
      background: var(--superficie);
      color: var(--tinta);
      box-shadow: 0 0 0 0.5px var(--linha-suave);
    }
    .grade a:hover {
      text-decoration: none;
      box-shadow: 0 0 0 1px var(--linha);
    }
    .data {
      flex: none;
      width: 56px;
      height: 56px;
      border-radius: 14px;
      background: var(--fundo-agrupado);
      display: grid;
      place-content: center;
      text-align: center;
      font-size: 0.75rem;
      color: var(--tinta-2);
      line-height: 1.1;
    }
    .data strong {
      font-family: var(--fonte-display);
      font-size: 1.5rem;
      color: var(--tinta);
    }
    .info {
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .info strong {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .vazio {
      padding: 64px 0;
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 14px;
      max-width: 520px;
    }
    .vazio h2 {
      font-size: clamp(2rem, 4vw, 3rem);
    }
    .vazio .botao {
      margin-top: 10px;
    }
  `,
})
export class Eventos implements OnInit {
  private readonly eventosService = inject(EventosService);

  readonly eventos = signal<EventoResumo[]>([]);
  readonly carregando = signal(true);

  /** Destaque: o próximo evento que ainda vai acontecer (ou o mais recente). */
  readonly proximo = computed(() => {
    const agora = Date.now();
    const lista = this.eventos().filter((e) => e.status !== 'CANCELADO');
    return lista.find((e) => new Date(e.data_hora).getTime() >= agora) ?? lista.at(-1) ?? null;
  });
  readonly outros = computed(() => this.eventos().filter((e) => e.id !== this.proximo()?.id));

  rotulo(status: string) {
    return ROTULO[status] ?? status;
  }

  async ngOnInit() {
    this.eventos.set(((await this.eventosService.listar()) ?? []) as EventoResumo[]);
    this.carregando.set(false);
  }
}
