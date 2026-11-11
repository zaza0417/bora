// Produção (Vercel).
// A chave publishable do Supabase é pública por design — a segurança vem do RLS.
export const environment = {
  production: true,
  // Provisório: trocar pelo endereço da API na VM (ex.: https://api.<ip>.sslip.io)
  apiUrl: 'https://api.seudominio.com.br',
  supabaseUrl: 'https://meknxehdggwmtyllvkmm.supabase.co',
  supabaseAnonKey: 'sb_publishable_jcrl8VQc6vZGzBUX76HC6A_y5J1cmC-',
};
