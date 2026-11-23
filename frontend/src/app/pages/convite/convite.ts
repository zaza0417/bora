import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, computed, DestroyRef, inject, input, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Observable } from 'rxjs';
import { ApiService, Convite, Pagamento, PixPresente, PresenteConvite } from '../../core/api.service';
import { Logo } from '../../shared/logo';

/** Duração presumida da festa no calendário (o evento só tem horário de início). */
const DURACAO_HORAS = 4;

/** Data em UTC no formato do iCalendar/Google: 20270116T220000Z */
function dataCalendario(d: Date) {
  return d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
}

/** Escapa texto para o .ics (RFC 5545). */
function textoIcs(s: string) {
  return s.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n');
}

/** Página pública do convidado: /c/:token (mobile-first). */
@Component({
  selector: 'app-convite',
  imports: [FormsModule, DatePipe, CurrencyPipe, Logo],
  styleUrl: './convite.scss',
  templateUrl: './convite.html',
})
export class ConvitePage implements OnInit {
  /** Vem da rota (withComponentInputBinding). */
  readonly token = input.required<string>();

  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);

  readonly convite = signal<Convite | null>(null);
  readonly pagamento = signal<Pagamento | null>(null);
  readonly erro = signal<string | null>(null);
  readonly enviando = signal(false);
  readonly copiado = signal(false);
  /** Explosão de confete quando a pessoa diz "Vou!" (o momento de festa da página). */
  readonly festa = signal(false);
  readonly confetes = Array.from({ length: 18 }, (_, i) => i);
  acompanhantes = 0;

  // Presentes
  readonly presenteEmDinheiro = signal<string | null>(null); // id do presente sendo pago
  readonly pixPresente = signal<PixPresente | null>(null);
  readonly ocupadoPresente = signal<string | null>(null);
  readonly pixPresenteCopiado = signal(false);
  valorPresente: number | null = null;

  readonly primeiroNome = computed(() => this.convite()?.convidado_nome.split(' ')[0] ?? '');
  readonly opcoesAcompanhantes = computed(() => {
    const max = this.convite()?.max_acompanhantes ?? 5;
    return Array.from({ length: max + 1 }, (_, i) => i);
  });

  private polling?: ReturnType<typeof setInterval>;

  ngOnInit() {
    this.destroyRef.onDestroy(() => clearInterval(this.polling));
    this.api.convite(this.token()).subscribe({
      next: (c) => {
        this.convite.set(c);
        this.acompanhantes = c.qtd_acompanhantes;
        if (c.comprovante_recebido && c.status !== 'CONFIRMADO') this.acompanharConvite();
      },
      error: () => this.erro.set('Convite não encontrado.'),
    });
  }

  responder(vou: boolean) {
    this.enviando.set(true);
    this.erro.set(null);
    this.api.responder(this.token(), vou, this.acompanhantes).subscribe({
      next: (c) => {
        this.convite.set(c);
        this.pagamento.set(null);
        this.enviando.set(false);
        if (vou) this.comemorar();
      },
      error: (e) => this.falha(e),
    });
  }

  pagar() {
    this.enviando.set(true);
    this.erro.set(null);
    this.api.gerarPagamento(this.token()).subscribe({
      next: (p) => {
        this.pagamento.set(p);
        this.enviando.set(false);
        if (p.modo === 'MERCADO_PAGO' && p.pagamento_id) this.acompanharPagamento(p.pagamento_id);
        else this.acompanharConvite();
      },
      error: (e) => this.falha(e),
    });
  }

  private comemorar() {
    this.festa.set(false);
    requestAnimationFrame(() => this.festa.set(true));
    setTimeout(() => this.festa.set(false), 1800);
  }

  /** Converte "2027-01-16" → Date sem cair no dia anterior por causa do fuso. */
  dataLocal(iso: string) {
    return new Date(iso + 'T12:00:00');
  }

  async copiarPix() {
    const codigo = this.pagamento()?.pix_copia_cola;
    if (!codigo) return;
    await navigator.clipboard.writeText(codigo);
    this.copiado.set(true);
    setTimeout(() => this.copiado.set(false), 2500);
  }

  /** Modo PIX manual: espera o comprovante chegar / o organizador confirmar. */
  private acompanharConvite() {
    clearInterval(this.polling);
    this.polling = setInterval(() => {
      this.api.convite(this.token()).subscribe((c) => {
        this.convite.set(c);
        if (c.status === 'CONFIRMADO') {
          clearInterval(this.polling);
          this.pagamento.set(null);
          this.comemorar();
        }
      });
    }, 5000);
  }

  private acompanharPagamento(id: string) {
    clearInterval(this.polling);
    this.polling = setInterval(() => {
      this.api.statusPagamento(this.token(), id).subscribe((s) => {
        if (s.convidado_status === 'CONFIRMADO') {
          clearInterval(this.polling);
          this.convite.update((c) => (c ? { ...c, status: 'CONFIRMADO' } : c));
          this.pagamento.set(null);
        } else if (s.status !== 'PENDENTE') {
          clearInterval(this.polling);
        }
      });
    }, 5000);
  }

  // --- presentes ---
  podeReservar(p: PresenteConvite) {
    return p.modo !== 'DINHEIRO';
  }

  podeDarDinheiro(p: PresenteConvite) {
    return p.modo !== 'RESERVA' && !!this.convite()?.presente_em_dinheiro;
  }

  progresso(p: PresenteConvite) {
    return p.valor_referencia ? Math.min(100, (+p.arrecadado / +p.valor_referencia) * 100) : 0;
  }

  reservar(p: PresenteConvite) {
    this.acaoPresente(p, this.api.reservarPresente(this.token(), p.id));
  }

  desistir(p: PresenteConvite) {
    this.acaoPresente(p, this.api.cancelarReserva(this.token(), p.id));
  }

  abrirDinheiro(p: PresenteConvite) {
    const aberto = this.presenteEmDinheiro() === p.id;
    this.presenteEmDinheiro.set(aberto ? null : p.id);
    this.pixPresente.set(null);
    this.valorPresente = null;
  }

  gerarPixPresente(p: PresenteConvite) {
    if (!this.valorPresente) return;
    this.ocupadoPresente.set(p.id);
    this.erro.set(null);
    this.api.pixPresente(this.token(), p.id, this.valorPresente).subscribe({
      next: (pix) => {
        this.pixPresente.set(pix);
        this.ocupadoPresente.set(null);
      },
      error: (e) => this.falhaPresente(e),
    });
  }

  async copiarPixPresente() {
    const codigo = this.pixPresente()?.pix_copia_cola;
    if (!codigo) return;
    await navigator.clipboard.writeText(codigo);
    this.pixPresenteCopiado.set(true);
    setTimeout(() => this.pixPresenteCopiado.set(false), 2500);
  }

  avisarPago(p: PresenteConvite) {
    const valor = Number(this.pixPresente()?.valor ?? this.valorPresente);
    if (!valor) return;
    this.acaoPresente(p, this.api.avisarPresentePago(this.token(), p.id, valor), () => {
      this.presenteEmDinheiro.set(null);
      this.pixPresente.set(null);
      this.valorPresente = null;
    });
  }

  private acaoPresente(
    p: PresenteConvite,
    req: Observable<Convite>,
    depois?: () => void,
  ) {
    this.ocupadoPresente.set(p.id);
    this.erro.set(null);
    req.subscribe({
      next: (c) => {
        this.convite.set(c);
        this.ocupadoPresente.set(null);
        depois?.();
      },
      error: (e) => this.falhaPresente(e),
    });
  }

  private falhaPresente(e: { error?: { detail?: string } }) {
    this.ocupadoPresente.set(null);
    this.erro.set(e.error?.detail ?? 'Não deu agora. Confira sua internet e tente de novo.');
    // Alguém pode ter escolhido o mesmo presente: atualiza a lista
    this.api.convite(this.token()).subscribe((c) => this.convite.set(c));
  }

  // --- agenda ---
  private janelaEvento() {
    const c = this.convite()!;
    const inicio = new Date(c.data_hora);
    const fim = new Date(inicio.getTime() + DURACAO_HORAS * 3600_000);
    const local = [c.local_nome, c.endereco].filter(Boolean).join(', ');
    return { c, inicio, fim, local, link: location.href };
  }

  /** Baixa um .ics: no iPhone abre direto o "Adicionar ao Calendário". */
  adicionarAgenda() {
    const { c, inicio, fim, local, link } = this.janelaEvento();
    const linhas = [
      'BEGIN:VCALENDAR',
      'VERSION:2.0',
      'PRODID:-//Bora//Convite//PT-BR',
      'CALSCALE:GREGORIAN',
      'METHOD:PUBLISH',
      'BEGIN:VEVENT',
      `UID:${this.token()}@bora`,
      `DTSTAMP:${dataCalendario(new Date())}`,
      `DTSTART:${dataCalendario(inicio)}`,
      `DTEND:${dataCalendario(fim)}`,
      `SUMMARY:${textoIcs(c.evento_nome)}`,
      ...(local ? [`LOCATION:${textoIcs(local)}`] : []),
      `DESCRIPTION:${textoIcs((c.evento_descricao ? c.evento_descricao + '\n\n' : '') + 'Convite: ' + link)}`,
      `URL:${link}`,
      'BEGIN:VALARM',
      'TRIGGER:-PT3H',
      'ACTION:DISPLAY',
      `DESCRIPTION:${textoIcs(c.evento_nome)}`,
      'END:VALARM',
      'END:VEVENT',
      'END:VCALENDAR',
    ];
    const blob = new Blob([linhas.join('\r\n')], { type: 'text/calendar;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = c.evento_nome.replace(/[^\p{L}\p{N} ]/gu, '').trim().replace(/\s+/g, '-').toLowerCase() + '.ics';
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  googleAgenda() {
    const { c, inicio, fim, local, link } = this.janelaEvento();
    const q = new URLSearchParams({
      action: 'TEMPLATE',
      text: c.evento_nome,
      dates: `${dataCalendario(inicio)}/${dataCalendario(fim)}`,
      details: (c.evento_descricao ? c.evento_descricao + '\n\n' : '') + 'Convite: ' + link,
      location: local,
    });
    return `https://calendar.google.com/calendar/render?${q}`;
  }

  private falha(e: { error?: { detail?: string } }) {
    this.enviando.set(false);
    this.erro.set(e.error?.detail ?? 'Não deu para enviar agora. Confira sua internet e tente de novo.');
  }
}
