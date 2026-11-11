import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { environment } from '../../environments/environment';

export type StatusConvidado = 'CONVIDADO' | 'AGUARDANDO_PAGAMENTO' | 'CONFIRMADO' | 'RECUSOU';

export interface ItemSimples {
  nome: string;
  descricao: string | null;
}

export interface Convite {
  convidado_nome: string;
  status: StatusConvidado;
  qtd_acompanhantes: number;
  max_acompanhantes: number | null;
  evento_nome: string;
  evento_descricao: string | null;
  data_hora: string;
  local_nome: string | null;
  endereco: string | null;
  mapa_url: string | null;
  capa_url: string | null;
  convite_imagem_url: string | null;
  tem_contribuicao: boolean;
  colaboracoes: { descricao: string; valor_por_pessoa: string }[];
  atracoes: ItemSimples[];
  cardapio: ItemSimples[];
  valor_devido: string;
  valor_cobrado: string | null;
  modo_pagamento: 'MERCADO_PAGO' | 'PIX_MANUAL' | 'NENHUM';
  comprovante_recebido: boolean;
  prazo_pagamento: string | null;
  prazo_vencido: boolean;
}

export interface Pagamento {
  modo: 'MERCADO_PAGO' | 'PIX_MANUAL';
  valor: string;
  pix_copia_cola: string | null;
  pix_qr_base64: string | null;
  status: string;
  pagamento_id: string | null;
  expira_em: string | null;
  pix_chave: string | null;
  pix_nome: string | null;
  whatsapp_url: string | null;
}

export interface ComprovanteLinha {
  convidado_id: string;
  nome: string;
  telefone_e164: string;
  valor_devido: string;
  recebido_em: string;
  imagem_url: string | null;
  analise: AnaliseComprovante | null;
}

export interface AnaliseComprovante {
  texto_legivel: boolean;
  valor_confere: boolean;
  data_confere: boolean;
  recebedor_confere: boolean | null;
  convidado_confere: boolean;
  repetido: boolean;
  tudo_confere: boolean;
  valores_encontrados: string[];
  datas_encontradas: string[];
  e2e: string | null;
}

export interface ConvidadoLinha {
  id: string;
  nome: string;
  telefone_e164: string;
  status: StatusConvidado;
  qtd_acompanhantes: number;
  valor_devido: string;
  opt_out: boolean;
  link: string;
  convidado_em: string;
  confirmado_em: string | null;
  ultima_mensagem_status: string | null;
  comprovante_recebido_em: string | null;
}

export interface Painel {
  por_status: Partial<Record<StatusConvidado, number>>;
  pessoas_confirmadas: number;
  prazo_vencido_pendentes: number;
  arrecadado_total: string;
  colaboracoes: { descricao: string; tipo: string; meta: string | null; arrecadado: string; projetado: string }[];
  mensagens_com_falha: number;
  comprovantes_pendentes: number;
}

export interface StatusWhatsapp {
  status: 'CONECTADO' | 'DESCONECTADO' | 'AGUARDANDO_QR' | 'NAO_CONFIGURADO';
  numero: string | null;
  qr_base64: string | null;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiUrl;

  // --- convidado (público, via token) ---
  convite(token: string) {
    return this.http.get<Convite>(`${this.base}/convites/${token}`);
  }

  responder(token: string, vou: boolean, qtd_acompanhantes: number) {
    return this.http.post<Convite>(`${this.base}/convites/${token}/resposta`, {
      vou,
      qtd_acompanhantes,
    });
  }

  gerarPagamento(token: string) {
    return this.http.post<Pagamento>(`${this.base}/convites/${token}/pagamento`, {});
  }

  statusPagamento(token: string, pagamentoId: string) {
    return this.http.get<{ status: string; convidado_status: StatusConvidado }>(
      `${this.base}/convites/${token}/pagamento/${pagamentoId}/status`,
    );
  }

  // --- organizador (autenticado) ---
  eu() {
    return this.http.get<{
      id: string;
      email: string | null;
      mercado_pago_conectado: boolean;
      whatsapp_status: string | null;
    }>(`${this.base}/eu`);
  }

  adicionarConvidado(eventoId: string, nome: string, telefone: string) {
    return this.http.post<{ id: string; link: string }>(`${this.base}/eventos/${eventoId}/convidados`, { nome, telefone });
  }

  ativarEvento(eventoId: string) {
    return this.http.post<{ status: string; prazo_pagamento: string | null; convites_enfileirados: number }>(
      `${this.base}/eventos/${eventoId}/ativar`,
      {},
    );
  }

  cancelarEvento(eventoId: string) {
    return this.http.post<{ status: string; avisados: number }>(`${this.base}/eventos/${eventoId}/cancelar`, {});
  }

  recalcularPrazo(eventoId: string) {
    return this.http.post(`${this.base}/eventos/${eventoId}/prazo/recalcular`, {});
  }

  painel(eventoId: string) {
    return this.http.get<Painel>(`${this.base}/eventos/${eventoId}/painel`);
  }

  convidados(eventoId: string) {
    return this.http.get<ConvidadoLinha[]>(`${this.base}/eventos/${eventoId}/convidados`);
  }

  reenviarConvite(eventoId: string, convidadoId: string) {
    return this.http.post(`${this.base}/eventos/${eventoId}/convidados/${convidadoId}/reenviar`, {});
  }

  removerConvidado(eventoId: string, convidadoId: string) {
    return this.http.delete(`${this.base}/eventos/${eventoId}/convidados/${convidadoId}`);
  }

  comprovantes(eventoId: string) {
    return this.http.get<ComprovanteLinha[]>(`${this.base}/eventos/${eventoId}/comprovantes`);
  }

  recusarComprovante(eventoId: string, convidadoId: string) {
    return this.http.post(`${this.base}/eventos/${eventoId}/convidados/${convidadoId}/comprovante/recusar`, {});
  }

  baixaManual(eventoId: string, convidadoId: string, valor: number, observacao: string | null) {
    return this.http.post(`${this.base}/eventos/${eventoId}/convidados/${convidadoId}/baixa-manual`, {
      valor,
      observacao,
    });
  }

  // --- integrações ---
  mpAutorizar() {
    return this.http.get<{ url: string }>(`${this.base}/integracoes/mercadopago/autorizar`);
  }

  mpDesconectar() {
    return this.http.delete(`${this.base}/integracoes/mercadopago`);
  }

  whatsappConectar() {
    return this.http.post<StatusWhatsapp>(`${this.base}/integracoes/whatsapp/conectar`, {});
  }

  whatsappStatus() {
    return this.http.get<StatusWhatsapp>(`${this.base}/integracoes/whatsapp/status`);
  }

  whatsappDesconectar() {
    return this.http.delete(`${this.base}/integracoes/whatsapp`);
  }
}
