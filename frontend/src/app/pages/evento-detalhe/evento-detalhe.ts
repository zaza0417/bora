import { CurrencyPipe, DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, input, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Topo } from '../../shared/topo';
import { firstValueFrom } from 'rxjs';
import { ApiService, ComprovanteLinha, ConvidadoLinha, Painel, StatusConvidado } from '../../core/api.service';
import { Evento, EventosService } from '../../core/eventos.service';

type Filtro = 'TODOS' | StatusConvidado;

export const ROTULO_STATUS: Record<StatusConvidado, string> = {
  CONVIDADO: 'Convidado',
  AGUARDANDO_PAGAMENTO: 'Aguardando pagamento',
  CONFIRMADO: 'Confirmado',
  RECUSOU: 'Não vai',
};

@Component({
  selector: 'app-evento-detalhe',
  imports: [Topo, FormsModule, RouterLink, DatePipe, CurrencyPipe],
  templateUrl: './evento-detalhe.html',
  styleUrl: './evento-detalhe.scss',
})
export class EventoDetalhe implements OnInit {
  readonly id = input.required<string>();

  private readonly api = inject(ApiService);
  private readonly eventos = inject(EventosService);

  readonly evento = signal<Evento | null>(null);
  readonly painel = signal<Painel | null>(null);
  readonly convidados = signal<ConvidadoLinha[]>([]);
  readonly comprovantes = signal<ComprovanteLinha[]>([]);
  readonly filtro = signal<Filtro>('TODOS');
  readonly busca = signal('');
  readonly erro = signal<string | null>(null);
  readonly aviso = signal<string | null>(null);
  readonly ocupado = signal(false);

  // Formulário de novo convidado
  novoNome = '';
  novoTelefone = '';

  // Baixa manual
  readonly baixaDe = signal<ConvidadoLinha | null>(null);
  baixaValor: number | null = null;
  baixaObs = '';

  readonly rotulo = ROTULO_STATUS;
  readonly filtros: Filtro[] = ['TODOS', 'CONVIDADO', 'AGUARDANDO_PAGAMENTO', 'CONFIRMADO', 'RECUSOU'];

  readonly convidadosFiltrados = computed(() => {
    const termo = this.busca().trim().toLowerCase();
    return this.convidados().filter(
      (c) =>
        (this.filtro() === 'TODOS' || c.status === this.filtro()) &&
        (!termo || c.nome.toLowerCase().includes(termo) || c.telefone_e164.includes(termo)),
    );
  });

  readonly total = computed(() => this.convidados().length);

  async ngOnInit() {
    await this.recarregar();
  }

  async recarregar() {
    try {
      const [dados, painel, convidados, comprovantes] = await Promise.all([
        this.eventos.carregar(this.id()),
        firstValueFrom(this.api.painel(this.id())),
        firstValueFrom(this.api.convidados(this.id())),
        firstValueFrom(this.api.comprovantes(this.id())),
      ]);
      this.evento.set(dados.evento);
      this.painel.set(painel);
      this.convidados.set(convidados);
      this.comprovantes.set(comprovantes);
    } catch (e) {
      this.erro.set(this.mensagem(e));
    }
  }

  contagem(status: StatusConvidado) {
    return this.painel()?.por_status[status] ?? 0;
  }

  // --- evento ---
  async ativar() {
    await this.executar(async () => {
      const r = await firstValueFrom(this.api.ativarEvento(this.id()));
      this.aviso.set(
        `Evento ativo! ${r.convites_enfileirados} convite(s) na fila de envio.` +
          (r.prazo_pagamento ? ` Prazo de pagamento: ${r.prazo_pagamento.split('-').reverse().join('/')}.` : ''),
      );
    });
  }

  async cancelar() {
    if (!confirm('Cancelar o evento? Todos os convidados que não recusaram serão avisados pelo WhatsApp.')) return;
    await this.executar(async () => {
      const r = await firstValueFrom(this.api.cancelarEvento(this.id()));
      this.aviso.set(`Evento cancelado. ${r.avisados} convidado(s) serão avisados.`);
    });
  }

  // --- convidados ---
  async adicionar() {
    if (!this.novoNome.trim() || !this.novoTelefone.trim()) return;
    await this.executar(async () => {
      await firstValueFrom(this.api.adicionarConvidado(this.id(), this.novoNome, this.novoTelefone));
      this.aviso.set(
        this.evento()?.status === 'ATIVO'
          ? `${this.novoNome} adicionado(a) — convite na fila de envio.`
          : `${this.novoNome} adicionado(a). O convite sai quando você ativar o evento.`,
      );
      this.novoNome = '';
      this.novoTelefone = '';
    });
  }

  async reenviar(c: ConvidadoLinha) {
    await this.executar(async () => {
      await firstValueFrom(this.api.reenviarConvite(this.id(), c.id));
      this.aviso.set(`Convite de ${c.nome} colocado na fila de novo.`);
    });
  }

  async remover(c: ConvidadoLinha) {
    if (!confirm(`Remover ${c.nome} da lista?`)) return;
    await this.executar(async () => {
      await firstValueFrom(this.api.removerConvidado(this.id(), c.id));
      this.aviso.set(`${c.nome} removido(a).`);
    });
  }

  async copiarLink(c: ConvidadoLinha) {
    await navigator.clipboard.writeText(c.link);
    this.aviso.set(`Link de ${c.nome} copiado`);
    clearTimeout(this.timerAviso);
    this.timerAviso = setTimeout(() => this.aviso.set(null), 2500);
  }

  async confirmarComprovante(r: ComprovanteLinha) {
    await this.executar(async () => {
      await firstValueFrom(
        this.api.baixaManual(this.id(), r.convidado_id, Number(r.valor_devido), 'Comprovante pelo WhatsApp'),
      );
      this.aviso.set(`${r.nome} confirmado(a) — aviso enviado pelo WhatsApp.`);
    });
  }

  async recusarComprovante(r: ComprovanteLinha) {
    if (!confirm(`Descartar o comprovante de ${r.nome}? A pessoa continua como pendente.`)) return;
    await this.executar(async () => {
      await firstValueFrom(this.api.recusarComprovante(this.id(), r.convidado_id));
      this.aviso.set(`Comprovante de ${r.nome} descartado.`);
    });
  }

  abrirBaixa(c: ConvidadoLinha) {
    this.baixaDe.set(c);
    this.baixaValor = Number(c.valor_devido);
    this.baixaObs = '';
  }

  async confirmarBaixa() {
    const c = this.baixaDe();
    if (!c || !this.baixaValor) return;
    await this.executar(async () => {
      await firstValueFrom(this.api.baixaManual(this.id(), c.id, this.baixaValor!, this.baixaObs || null));
      this.aviso.set(`Pagamento de ${c.nome} registrado — presença confirmada.`);
      this.baixaDe.set(null);
    });
  }

  // --- util ---
  private timerAviso?: ReturnType<typeof setTimeout>;

  /** Fecha o menu "⋯" depois de escolher uma ação. */
  fecharMenu(ev: Event) {
    (ev.currentTarget as HTMLElement).closest('details')?.removeAttribute('open');
  }

  private async executar(acao: () => Promise<void>) {
    this.ocupado.set(true);
    this.erro.set(null);
    this.aviso.set(null);
    try {
      await acao();
      await this.recarregar();
      clearTimeout(this.timerAviso);
      this.timerAviso = setTimeout(() => this.aviso.set(null), 3500);
    } catch (e) {
      this.erro.set(this.mensagem(e));
    } finally {
      this.ocupado.set(false);
    }
  }

  private mensagem(e: unknown): string {
    if (e instanceof HttpErrorResponse) {
      const detalhe = e.error?.detail;
      if (typeof detalhe === 'string') return detalhe;
      if (Array.isArray(detalhe)) return detalhe.map((d) => d.msg).join('; ');
      return e.status === 0 ? 'Não foi possível falar com o servidor.' : `Erro ${e.status}`;
    }
    return (e as Error)?.message ?? 'Erro inesperado';
  }
}
