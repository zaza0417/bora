import { Routes } from '@angular/router';
import { authGuard } from './core/auth';

export const routes: Routes = [
  // Público — link do convite enviado no WhatsApp
  { path: 'c/:token', loadComponent: () => import('./pages/convite/convite').then((m) => m.ConvitePage) },

  // Organizador
  { path: 'login', loadComponent: () => import('./pages/login/login').then((m) => m.Login) },
  {
    path: 'eventos',
    canActivate: [authGuard],
    children: [
      { path: '', loadComponent: () => import('./pages/eventos/eventos').then((m) => m.Eventos) },
      { path: 'novo', loadComponent: () => import('./pages/evento-form/evento-form').then((m) => m.EventoForm) },
      {
        path: ':id',
        loadComponent: () => import('./pages/evento-detalhe/evento-detalhe').then((m) => m.EventoDetalhe),
      },
      {
        path: ':id/editar',
        loadComponent: () => import('./pages/evento-form/evento-form').then((m) => m.EventoForm),
      },
    ],
  },

  {
    path: 'configuracoes',
    canActivate: [authGuard],
    loadComponent: () => import('./pages/configuracoes/configuracoes').then((m) => m.Configuracoes),
  },

  { path: '', pathMatch: 'full', loadComponent: () => import('./pages/inicio/inicio').then((m) => m.Inicio) },
  { path: '**', redirectTo: '' },
];
