import { inject, Injectable } from '@angular/core';
import { SupabaseService } from './supabase.service';

export type StatusEvento = 'RASCUNHO' | 'ATIVO' | 'ENCERRADO' | 'CANCELADO';
export type TipoColaboracao = 'FIXO' | 'RATEIO';

export interface Evento {
  id?: string;
  nome: string;
  descricao: string | null;
  local_nome: string | null;
  endereco: string | null;
  mapa_url: string | null;
  data_hora: string;
  convite_imagem_url: string | null;
  tem_contribuicao: boolean;
  max_acompanhantes: number | null;
  prazo_pagamento: string | null;
  prazo_manual: boolean;
  status?: StatusEvento;
}

export interface ColaboracaoForm {
  id?: string;
  descricao: string;
  tipo: TipoColaboracao;
  valor_por_pessoa: number | null;
  meta: number | null;
  pessoas_estimadas: number | null;
  ordem?: number;
}

export interface AtracaoForm {
  id?: string;
  nome: string;
  descricao: string | null;
  horario: string | null;
  ordem?: number;
}

export interface ItemCardapioForm {
  id?: string;
  categoria: string | null;
  nome: string;
  descricao: string | null;
  ordem?: number;
}

export interface EventoCompleto {
  evento: Evento;
  colaboracoes: ColaboracaoForm[];
  atracoes: AtracaoForm[];
  cardapio: ItemCardapioForm[];
}

const CAMPOS_EVENTO =
  'id, nome, descricao, local_nome, endereco, mapa_url, data_hora, convite_imagem_url, ' +
  'tem_contribuicao, max_acompanhantes, prazo_pagamento, prazo_manual, status';

/** Mesmo arredondamento do backend (app/domain/valores.py): rateio sobe para o real inteiro. */
export function valorPorPessoa(c: ColaboracaoForm): number | null {
  if (c.tipo === 'FIXO') return c.valor_por_pessoa && c.valor_por_pessoa > 0 ? c.valor_por_pessoa : null;
  if (!c.meta || !c.pessoas_estimadas || c.meta <= 0 || c.pessoas_estimadas <= 0) return null;
  return Math.ceil(c.meta / c.pessoas_estimadas);
}

/** Valor com a taxa do PIX repassada (backend: valor_com_taxa). */
export function comTaxa(valor: number, taxa = 0.0099): number {
  return Math.ceil(Math.round((valor / (1 - taxa)) * 1e6) / 1e4) / 100;
}

/**
 * CRUD do evento direto no Supabase (protegido por RLS).
 * Regras com efeito colateral (ativar, convidados, cancelar) ficam no backend → ApiService.
 */
@Injectable({ providedIn: 'root' })
export class EventosService {
  private readonly sb = inject(SupabaseService).client;

  async listar() {
    const { data, error } = await this.sb
      .from('evento')
      .select('id, nome, data_hora, status, local_nome, convite_imagem_url')
      .order('data_hora');
    if (error) throw error;
    return data;
  }

  async carregar(id: string): Promise<EventoCompleto> {
    const [ev, col, atr, car] = await Promise.all([
      this.sb.from('evento').select(CAMPOS_EVENTO).eq('id', id).single(),
      this.sb.from('colaboracao').select('*').eq('evento_id', id).order('ordem'),
      this.sb.from('atracao').select('*').eq('evento_id', id).order('ordem'),
      this.sb.from('item_cardapio').select('*').eq('evento_id', id).order('ordem'),
    ]);
    for (const r of [ev, col, atr, car]) if (r.error) throw r.error;
    return {
      evento: ev.data as unknown as Evento,
      colaboracoes: (col.data ?? []).map(({ evento_id, ...c }) => c as ColaboracaoForm),
      atracoes: (atr.data ?? []).map(({ evento_id, ...a }) => a as AtracaoForm),
      cardapio: (car.data ?? []).map(({ evento_id, ...i }) => i as ItemCardapioForm),
    };
  }

  /** Cria ou atualiza o evento e sincroniza as listas filhas. Retorna o id. */
  async salvar(dados: EventoCompleto): Promise<string> {
    const { id, status, ...campos } = dados.evento;
    const usuario = (await this.sb.auth.getUser()).data.user;
    if (!usuario) throw new Error('Sessão expirada');

    let eventoId = id;
    if (eventoId) {
      const { error } = await this.sb.from('evento').update(campos).eq('id', eventoId);
      if (error) throw error;
    } else {
      const { data, error } = await this.sb
        .from('evento')
        .insert({ ...campos, organizador_id: usuario.id })
        .select('id')
        .single();
      if (error) throw error;
      eventoId = data.id as string;
    }

    await this.sincronizar('colaboracao', eventoId, dados.evento.tem_contribuicao ? dados.colaboracoes : []);
    await this.sincronizar('atracao', eventoId, dados.atracoes);
    await this.sincronizar('item_cardapio', eventoId, dados.cardapio);
    return eventoId;
  }

  /**
   * Upsert dos itens + remoção dos que saíram da lista.
   * (Colaborações não são recriadas, para não perder o snapshot de valores dos convidados.)
   */
  private async sincronizar(
    tabela: 'colaboracao' | 'atracao' | 'item_cardapio',
    eventoId: string,
    itens: { id?: string }[],
  ) {
    const { data: atuais, error } = await this.sb.from(tabela).select('id').eq('evento_id', eventoId);
    if (error) throw error;

    const manter = new Set(itens.filter((i) => i.id).map((i) => i.id));
    const remover = (atuais ?? []).map((a) => a.id as string).filter((x) => !manter.has(x));
    if (remover.length) {
      const r = await this.sb.from(tabela).delete().in('id', remover);
      if (r.error) throw r.error;
    }

    const linhas = itens.map((item, ordem) => ({ ...item, evento_id: eventoId, ordem }));
    const existentes = linhas.filter((l) => l.id);
    const novos = linhas.filter((l) => !l.id).map(({ id, ...l }) => l);
    if (existentes.length) {
      const r = await this.sb.from(tabela).upsert(existentes);
      if (r.error) throw r.error;
    }
    if (novos.length) {
      const r = await this.sb.from(tabela).insert(novos);
      if (r.error) throw r.error;
    }
  }

  /** Sobe a arte do convite no bucket público "capas" (pasta = id do organizador). */
  async enviarArte(arquivo: File): Promise<string> {
    const usuario = (await this.sb.auth.getUser()).data.user;
    if (!usuario) throw new Error('Sessão expirada');
    const ext = arquivo.name.split('.').pop()?.toLowerCase() ?? 'jpg';
    const caminho = `${usuario.id}/convite-${crypto.randomUUID()}.${ext}`;
    const { error } = await this.sb.storage
      .from('capas')
      .upload(caminho, arquivo, { contentType: arquivo.type, upsert: false });
    if (error) throw error;
    return this.sb.storage.from('capas').getPublicUrl(caminho).data.publicUrl;
  }
}
