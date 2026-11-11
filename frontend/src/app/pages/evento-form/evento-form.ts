import { CurrencyPipe } from '@angular/common';
import { Component, computed, inject, input, OnInit, signal, WritableSignal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { Topo } from '../../shared/topo';
import { ApiService } from '../../core/api.service';
import {
  AtracaoForm,
  ColaboracaoForm,
  comTaxa,
  Evento,
  EventosService,
  ItemCardapioForm,
  valorPorPessoa,
} from '../../core/eventos.service';

const FUSO = 'America/Sao_Paulo';
const TAMANHO_MAX_ARTE = 5 * 1024 * 1024;

/** Converte timestamptz → {data: 'yyyy-mm-dd', hora: 'HH:mm'} no fuso de Brasília. */
function separarDataHora(iso: string): { data: string; hora: string } {
  const partes = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: FUSO,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    })
      .formatToParts(new Date(iso))
      .map((p) => [p.type, p.value]),
  );
  return { data: `${partes['year']}-${partes['month']}-${partes['day']}`, hora: `${partes['hour']}:${partes['minute']}` };
}

/** Brasil não tem horário de verão desde 2019 → offset fixo -03:00. */
function juntarDataHora(data: string, hora: string): string {
  return `${data}T${hora}:00-03:00`;
}

@Component({
  selector: 'app-evento-form',
  imports: [Topo, FormsModule, RouterLink, CurrencyPipe],
  templateUrl: './evento-form.html',
  styleUrl: './evento-form.scss',
})
export class EventoForm implements OnInit {
  /** Vem da rota: /eventos/:id/editar. Ausente em /eventos/novo. */
  readonly id = input<string>();

  private readonly eventos = inject(EventosService);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  readonly carregando = signal(false);
  readonly salvando = signal(false);
  readonly enviandoArte = signal(false);
  readonly erro = signal<string | null>(null);

  evento: Evento = {
    nome: '',
    descricao: null,
    local_nome: null,
    endereco: null,
    mapa_url: null,
    data_hora: '',
    convite_imagem_url: null,
    tem_contribuicao: false,
    max_acompanhantes: null,
    prazo_pagamento: null,
    prazo_manual: false,
  };
  data = '';
  hora = '19:00';
  readonly arteUrl = signal<string | null>(null);
  readonly colaboracoes = signal<ColaboracaoForm[]>([]);
  readonly atracoes = signal<AtracaoForm[]>([]);
  readonly cardapio = signal<ItemCardapioForm[]>([]);

  readonly totalPorPessoa = computed(() =>
    this.colaboracoes().reduce((soma, c) => soma + (valorPorPessoa(c) ?? 0), 0),
  );
  readonly totalComTaxa = computed(() => (this.totalPorPessoa() > 0 ? comTaxa(this.totalPorPessoa()) : 0));
  readonly valorPorPessoa = valorPorPessoa;

  async ngOnInit() {
    const id = this.id();
    if (!id) return;
    this.carregando.set(true);
    try {
      const dados = await this.eventos.carregar(id);
      this.evento = dados.evento;
      ({ data: this.data, hora: this.hora } = separarDataHora(dados.evento.data_hora));
      this.arteUrl.set(dados.evento.convite_imagem_url);
      this.colaboracoes.set(dados.colaboracoes);
      this.atracoes.set(dados.atracoes);
      this.cardapio.set(dados.cardapio);
    } catch (e) {
      this.erro.set((e as Error).message);
    } finally {
      this.carregando.set(false);
    }
  }

  // --- arte do convite ---
  async escolherArte(ev: Event) {
    const arquivo = (ev.target as HTMLInputElement).files?.[0];
    if (!arquivo) return;
    if (!arquivo.type.startsWith('image/')) return this.erro.set('Envie uma imagem (JPG ou PNG).');
    if (arquivo.size > TAMANHO_MAX_ARTE) return this.erro.set('A imagem deve ter até 5 MB.');
    this.enviandoArte.set(true);
    this.erro.set(null);
    try {
      this.arteUrl.set(await this.eventos.enviarArte(arquivo));
    } catch (e) {
      this.erro.set('Falha ao enviar a imagem: ' + (e as Error).message);
    } finally {
      this.enviandoArte.set(false);
    }
  }

  removerArte() {
    this.arteUrl.set(null);
  }

  // --- listas ---
  adicionarColaboracao() {
    this.colaboracoes.update((l) => [
      ...l,
      { descricao: '', tipo: 'FIXO', valor_por_pessoa: null, meta: null, pessoas_estimadas: null },
    ]);
  }

  adicionarAtracao() {
    this.atracoes.update((l) => [...l, { nome: '', descricao: null, horario: null }]);
  }

  adicionarItem() {
    this.cardapio.update((l) => [...l, { categoria: null, nome: '', descricao: null }]);
  }

  remover<T>(lista: WritableSignal<T[]>, indice: number) {
    lista.update((l) => l.filter((_, i) => i !== indice));
  }

  /** Força o recálculo dos computed após editar um campo dentro da lista. */
  tocar<T>(lista: WritableSignal<T[]>) {
    lista.update((l) => [...l]);
  }

  // --- salvar ---
  private validar(): string | null {
    if (!this.evento.nome.trim()) return 'Informe o nome do evento.';
    if (!this.data || !this.hora) return 'Informe a data e a hora.';
    if (this.evento.tem_contribuicao) {
      if (this.colaboracoes().length === 0) return 'Adicione ao menos uma colaboração.';
      for (const c of this.colaboracoes()) {
        if (!c.descricao.trim()) return 'Toda colaboração precisa de uma descrição.';
        if (valorPorPessoa(c) === null) {
          return c.tipo === 'FIXO'
            ? `Informe o valor por pessoa de "${c.descricao}".`
            : `Informe a meta e o número estimado de pessoas de "${c.descricao}".`;
        }
      }
      if (this.evento.prazo_manual && !this.evento.prazo_pagamento) return 'Informe o prazo de pagamento.';
    }
    if (this.atracoes().some((a) => !a.nome.trim())) return 'Toda atração precisa de um nome.';
    if (this.cardapio().some((i) => !i.nome.trim())) return 'Todo item do cardápio precisa de um nome.';
    return null;
  }

  async salvar() {
    const problema = this.validar();
    if (problema) return this.erro.set(problema);

    this.salvando.set(true);
    this.erro.set(null);
    const colabs = this.colaboracoes().map((c) => ({
      ...c,
      valor_por_pessoa: c.tipo === 'FIXO' ? c.valor_por_pessoa : null,
      meta: c.tipo === 'RATEIO' || c.meta ? c.meta : null,
      pessoas_estimadas: c.tipo === 'RATEIO' ? c.pessoas_estimadas : null,
    }));
    try {
      const novaDataHora = juntarDataHora(this.data, this.hora);
      const mudouData =
        !!this.evento.data_hora && new Date(this.evento.data_hora).getTime() !== new Date(novaDataHora).getTime();
      const id = await this.eventos.salvar({
        evento: {
          ...this.evento,
          data_hora: novaDataHora,
          convite_imagem_url: this.arteUrl(),
        },
        colaboracoes: colabs,
        atracoes: this.atracoes().map((a) => ({ ...a, horario: a.horario || null })),
        cardapio: this.cardapio(),
      });
      // Evento ativo com data alterada → recalcula o prazo automático no backend
      if (this.evento.status === 'ATIVO' && mudouData) {
        this.api.recalcularPrazo(id).subscribe();
      }
      await this.router.navigate(['/eventos', id]);
    } catch (e) {
      this.erro.set((e as Error).message);
    } finally {
      this.salvando.set(false);
    }
  }
}
