import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { Topo } from '../../shared/topo';
import { firstValueFrom } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { ApiService, StatusWhatsapp } from '../../core/api.service';
import { SupabaseService } from '../../core/supabase.service';

const MOTIVOS_MP: Record<string, string> = {
  autorizacao_cancelada: 'A autorização foi cancelada no Mercado Pago.',
  link_expirado: 'O link de autorização expirou. Tente conectar de novo.',
  falha_mercado_pago: 'O Mercado Pago recusou a conexão. Tente de novo em instantes.',
};

/** Conectar Mercado Pago (OAuth) e WhatsApp (QR Code) — RF-ORG-02..05. */
@Component({
  selector: 'app-configuracoes',
  imports: [Topo, FormsModule],
  templateUrl: './configuracoes.html',
  styleUrl: './configuracoes.scss',
})
export class Configuracoes implements OnInit {
  private readonly api = inject(ApiService);
  private readonly rota = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly supabase = inject(SupabaseService);

  readonly mpConectado = signal<boolean | null>(null);
  readonly whatsapp = signal<StatusWhatsapp | null>(null);
  readonly aviso = signal<string | null>(null);
  readonly erro = signal<string | null>(null);
  readonly ocupado = signal(false);

  // PIX manual (chave própria) — salvo na tabela organizador
  pix = { pix_chave: '', pix_nome: '', pix_cidade: '', telefone: '', baixa_automatica: false };
  readonly pixSalvo = signal(false);

  private polling?: ReturnType<typeof setInterval>;

  async ngOnInit() {
    this.destroyRef.onDestroy(() => clearInterval(this.polling));

    // Retorno do OAuth: /configuracoes?mp=ok | ?mp=erro&motivo=...
    const q = this.rota.snapshot.queryParamMap;
    if (q.get('mp') === 'ok') this.aviso.set('Mercado Pago conectado');
    if (q.get('mp') === 'erro') this.erro.set(MOTIVOS_MP[q.get('motivo') ?? ''] ?? 'Não foi possível conectar o Mercado Pago.');
    if (q.has('mp')) this.router.navigate([], { queryParams: {}, replaceUrl: true });

    await this.carregar();
  }

  private async carregar() {
    try {
      const [eu, wa, org] = await Promise.all([
        firstValueFrom(this.api.eu()),
        firstValueFrom(this.api.whatsappStatus()),
        this.supabase.client.from('organizador').select('pix_chave, pix_nome, pix_cidade, telefone, baixa_automatica').single(),
      ]);
      this.mpConectado.set(eu.mercado_pago_conectado);
      this.whatsapp.set(wa);
      if (org.data) {
        this.pix = {
          pix_chave: org.data.pix_chave ?? '',
          pix_nome: org.data.pix_nome ?? '',
          pix_cidade: org.data.pix_cidade ?? '',
          telefone: org.data.telefone ?? '',
          baixa_automatica: !!org.data.baixa_automatica,
        };
        this.pixSalvo.set(!!org.data.pix_chave);
      }
      if (wa.status === 'AGUARDANDO_QR') this.acompanharWhatsapp();
    } catch (e) {
      this.erro.set(this.mensagem(e));
    }
  }

  // --- PIX manual ---
  async salvarPix() {
    const chave = this.pix.pix_chave.trim();
    if (chave && (!this.pix.pix_nome.trim() || !this.pix.pix_cidade.trim())) {
      this.erro.set('Informe o nome do recebedor e a cidade (aparecem no app do banco de quem paga).');
      return;
    }
    await this.executar(async () => {
      const usuario = (await this.supabase.client.auth.getUser()).data.user;
      const { error } = await this.supabase.client
        .from('organizador')
        .update({
          pix_chave: chave || null,
          pix_nome: this.pix.pix_nome.trim() || null,
          pix_cidade: this.pix.pix_cidade.trim() || null,
          telefone: this.pix.telefone.trim() || null,
          baixa_automatica: this.pix.baixa_automatica,
        })
        .eq('id', usuario!.id);
      if (error) throw error;
      this.pixSalvo.set(!!chave);
      this.aviso.set(chave ? 'Ajustes salvos' : 'Chave PIX removida');
    });
  }

  // --- Mercado Pago ---
  async conectarMp() {
    await this.executar(async () => {
      const { url } = await firstValueFrom(this.api.mpAutorizar());
      window.location.href = url; // vai para o Mercado Pago e volta em /configuracoes?mp=ok
    });
  }

  async desconectarMp() {
    if (!confirm('Desconectar o Mercado Pago? Eventos com contribuição não poderão gerar PIX.')) return;
    await this.executar(async () => {
      await firstValueFrom(this.api.mpDesconectar());
      this.mpConectado.set(false);
      this.aviso.set('Mercado Pago desconectado.');
    });
  }

  // --- WhatsApp ---
  async conectarWhatsapp() {
    await this.executar(async () => {
      this.whatsapp.set(await firstValueFrom(this.api.whatsappConectar()));
      this.acompanharWhatsapp();
    });
  }

  async desconectarWhatsapp() {
    if (!confirm('Desconectar o WhatsApp? Convites e lembretes param de ser enviados.')) return;
    await this.executar(async () => {
      clearInterval(this.polling);
      await firstValueFrom(this.api.whatsappDesconectar());
      this.whatsapp.set({ status: 'NAO_CONFIGURADO', numero: null, qr_base64: null });
      this.aviso.set('WhatsApp desconectado.');
    });
  }

  /** Enquanto o QR estiver na tela, consulta o status a cada 3 s (o QR também se renova). */
  private acompanharWhatsapp() {
    clearInterval(this.polling);
    this.polling = setInterval(async () => {
      try {
        const wa = await firstValueFrom(this.api.whatsappStatus());
        this.whatsapp.update((atual) => ({ ...wa, qr_base64: wa.qr_base64 ?? atual?.qr_base64 ?? null }));
        if (wa.status === 'CONECTADO') {
          clearInterval(this.polling);
          this.aviso.set('WhatsApp conectado');
        } else if (wa.status !== 'AGUARDANDO_QR') {
          clearInterval(this.polling);
        }
      } catch {
        /* tenta de novo no próximo ciclo */
      }
    }, 3000);
  }

  formatarNumero(n: string | null) {
    if (!n) return '';
    const d = n.replace(/\D/g, '');
    return d.length === 13 ? `+${d.slice(0, 2)} (${d.slice(2, 4)}) ${d.slice(4, 9)}-${d.slice(9)}` : `+${d}`;
  }

  // --- util ---
  private timerAviso?: ReturnType<typeof setTimeout>;

  private async executar(acao: () => Promise<void>) {
    this.ocupado.set(true);
    this.erro.set(null);
    this.aviso.set(null);
    try {
      await acao();
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
      if (typeof e.error?.detail === 'string') return e.error.detail;
      return e.status === 0 ? 'Não foi possível falar com o servidor.' : `Erro ${e.status}`;
    }
    return (e as Error)?.message ?? 'Erro inesperado';
  }
}
