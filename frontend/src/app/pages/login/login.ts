import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { SupabaseService } from '../../core/supabase.service';
import { Logo } from '../../shared/logo';

const MENSAGENS: Record<string, string> = {
  'Invalid login credentials': 'E-mail ou senha não conferem.',
  'User already registered': 'Já existe uma conta com esse e-mail. Entre com sua senha.',
  'Password should be at least 6 characters': 'A senha precisa ter pelo menos 6 caracteres.',
};

@Component({
  selector: 'app-login',
  imports: [FormsModule, RouterLink, Logo],
  template: `
    <main class="tela">
      <aside class="lado-marca" aria-hidden="true">
        <a routerLink="/" class="voltar"><bora-logo [tamanho]="30" /></a>
        <p class="frase">Cada festa com a sua lista, a sua vaquinha e ninguém esquecido.</p>
      </aside>

      <section class="lado-form">
        <a routerLink="/" class="logo-celular"><bora-logo [tamanho]="30" /></a>
        <h1>{{ modoCadastro() ? 'Crie sua conta.' : 'Que bom te ver.' }}</h1>
        <p class="sub">
          {{ modoCadastro() ? 'Leva um minuto e você já cria o primeiro evento.' : 'Entre para ver seus eventos.' }}
        </p>

        <form (ngSubmit)="enviar()">
          @if (modoCadastro()) {
            <label class="sr-only" for="nome">Seu nome</label>
            <input id="nome" class="campo" name="nome" [(ngModel)]="nome" placeholder="Seu nome" autocomplete="name" required />
          }
          <label class="sr-only" for="email">E-mail</label>
          <input id="email" class="campo" name="email" type="email" [(ngModel)]="email" placeholder="voce@email.com" autocomplete="email" required />
          <label class="sr-only" for="senha">Senha</label>
          <input id="senha" class="campo" name="senha" type="password" [(ngModel)]="senha" placeholder="Senha"
            [attr.autocomplete]="modoCadastro() ? 'new-password' : 'current-password'" required minlength="6" />

          @if (erro()) {
            <p class="falha">{{ erro() }}</p>
          }

          <button type="submit" class="botao-grande botao-cheio" [disabled]="carregando()">
            {{ carregando() ? 'Um instante…' : modoCadastro() ? 'Criar conta' : 'Entrar' }}
          </button>
        </form>

        <p class="trocar">
          {{ modoCadastro() ? 'Já tem conta?' : 'Primeira vez aqui?' }}
          <button type="button" class="botao-texto" (click)="modoCadastro.set(!modoCadastro()); erro.set(null)">
            {{ modoCadastro() ? 'Entrar' : 'Criar conta' }}
          </button>
        </p>
      </section>
    </main>
  `,
  styles: `
    .tela {
      min-height: 100dvh;
      display: grid;
      grid-template-columns: 1fr 1fr;
    }
    .lado-marca {
      background: var(--marca);
      color: var(--sobre-marca);
      padding: 32px 48px 56px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .lado-marca bora-logo {
      --tinta: var(--sobre-marca);
    }
    .voltar:hover {
      text-decoration: none;
    }
    .frase {
      font-family: var(--fonte-display);
      font-weight: 800;
      font-size: clamp(2.4rem, 4vw, 4rem);
      letter-spacing: -0.05em;
      line-height: 0.98;
      max-width: 12ch;
    }
    .lado-form {
      width: 100%;
      max-width: 420px;
      margin: 0 auto;
      padding: 48px 22px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 10px;
    }
    .logo-celular {
      display: none;
      margin-bottom: 28px;
    }
    h1 {
      font-size: 2.6rem;
    }
    form {
      margin-top: 22px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    form button {
      margin-top: 8px;
    }
    .trocar {
      margin-top: 14px;
      color: var(--tinta-2);
      font-size: 0.94rem;
      text-align: center;
    }
    @media (max-width: 760px) {
      .tela {
        grid-template-columns: 1fr;
      }
      .lado-marca {
        display: none;
      }
      .logo-celular {
        display: inline-flex;
      }
      .lado-form {
        justify-content: flex-start;
        padding-top: 40px;
      }
    }
  `,
})
export class Login {
  private readonly supabase = inject(SupabaseService);
  private readonly router = inject(Router);

  nome = '';
  email = '';
  senha = '';
  readonly modoCadastro = signal(false);
  readonly carregando = signal(false);
  readonly erro = signal<string | null>(null);

  async enviar() {
    this.carregando.set(true);
    this.erro.set(null);
    const { error } = this.modoCadastro()
      ? await this.supabase.cadastrar(this.email, this.senha, this.nome)
      : await this.supabase.entrar(this.email, this.senha);
    this.carregando.set(false);
    if (error) {
      this.erro.set(MENSAGENS[error.message] ?? 'Não deu para entrar agora. Tente de novo em instantes.');
      return;
    }
    await this.router.navigateByUrl('/eventos');
  }
}
