import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, computed, DestroyRef, inject, input, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, Convite, Pagamento } from '../../core/api.service';
import { Logo } from '../../shared/logo';

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

  private falha(e: { error?: { detail?: string } }) {
    this.enviando.set(false);
    this.erro.set(e.error?.detail ?? 'Não deu para enviar agora. Confira sua internet e tente de novo.');
  }
}
