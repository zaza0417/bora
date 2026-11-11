import { Injectable, signal } from '@angular/core';
import { createClient, Session, SupabaseClient } from '@supabase/supabase-js';
import { environment } from '../../environments/environment';

/** Login do organizador + acesso direto às tabelas protegidas por RLS. */
@Injectable({ providedIn: 'root' })
export class SupabaseService {
  readonly client: SupabaseClient = createClient(environment.supabaseUrl, environment.supabaseAnonKey);
  readonly session = signal<Session | null>(null);
  private readonly pronto: Promise<void>;

  constructor() {
    this.pronto = this.client.auth.getSession().then(({ data }) => this.session.set(data.session));
    this.client.auth.onAuthStateChange((_evento, sessao) => this.session.set(sessao));
  }

  async sessaoAtual(): Promise<Session | null> {
    await this.pronto;
    return this.session();
  }

  entrar(email: string, senha: string) {
    return this.client.auth.signInWithPassword({ email, password: senha });
  }

  cadastrar(email: string, senha: string, nome: string) {
    return this.client.auth.signUp({ email, password: senha, options: { data: { nome } } });
  }

  sair() {
    return this.client.auth.signOut();
  }
}
