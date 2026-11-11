import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { environment } from '../../environments/environment';
import { SupabaseService } from './supabase.service';

/** Bloqueia rotas do organizador sem login. */
export const authGuard: CanActivateFn = async () => {
  // inject() só funciona antes do primeiro await (contexto de injeção)
  const supabase = inject(SupabaseService);
  const router = inject(Router);
  const sessao = await supabase.sessaoAtual();
  return sessao ? true : router.createUrlTree(['/login']);
};

/** Envia o JWT do Supabase para o backend (FastAPI). */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const token = inject(SupabaseService).session()?.access_token;
  if (!token || !req.url.startsWith(environment.apiUrl)) {
    return next(req);
  }
  return next(req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
};
