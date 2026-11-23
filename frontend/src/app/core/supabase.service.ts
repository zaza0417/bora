import { Injectable, signal } from '@angular/core';
import type { Session, SupabaseClient } from '@supabase/supabase-js';
import { environment } from '../../environments/environment';

/** Há uma sessão salva pelo Supabase neste navegador? (sem carregar a biblioteca) */
function temSessaoSalva(): boolean {
  try {
    return Object.keys(localStorage).some((k) => k.startsWith('sb-') && k.endsWith('-auth-token'));
  } catch {
    return false;
  }
}

/**
 * Login do organizador + acesso direto às tabelas protegidas por RLS.
 *
 * A biblioteca do Supabase é pesada e o convidado não precisa dela, então só é
 * baixada quando há login salvo ou quando uma tela do organizador pede.
 */
@Injectable({ providedIn: 'root' })
export class SupabaseService {
  readonly session = signal<Session | null>(null);
  private cliente?: SupabaseClient;
  private carregando?: Promise<SupabaseClient>;

  constructor() {
    if (temSessaoSalva()) void this.carregar();
  }

  /** Cliente já carregado. Use só depois do authGuard (ou de `carregar()`). */
  get client(): SupabaseClient {
    if (!this.cliente) throw new Error('Supabase ainda não foi carregado');
    return this.cliente;
  }

  carregar(): Promise<SupabaseClient> {
    this.carregando ??= import('@supabase/supabase-js').then(async ({ createClient }) => {
      const c = createClient(environment.supabaseUrl, environment.supabaseAnonKey);
      const { data } = await c.auth.getSession();
      this.session.set(data.session);
      c.auth.onAuthStateChange((_evento, sessao) => this.session.set(sessao));
      this.cliente = c;
      return c;
    });
    return this.carregando;
  }

  async sessaoAtual(): Promise<Session | null> {
    await this.carregar();
    return this.session();
  }

  async entrar(email: string, senha: string) {
    return (await this.carregar()).auth.signInWithPassword({ email, password: senha });
  }

  async cadastrar(email: string, senha: string, nome: string) {
    return (await this.carregar()).auth.signUp({ email, password: senha, options: { data: { nome } } });
  }

  async sair() {
    return (await this.carregar()).auth.signOut();
  }
}
