// Produção (Vercel).
// A chave publishable do Supabase é pública por design — a segurança vem do RLS.
export const environment = {
  production: true,
  // API na VM Oracle (Caddy + HTTPS). sslip.io resolve o IP 147.15.82.161.
  apiUrl: 'https://api.147-15-82-161.sslip.io',
  supabaseUrl: 'https://meknxehdggwmtyllvkmm.supabase.co',
  supabaseAnonKey: 'sb_publishable_jcrl8VQc6vZGzBUX76HC6A_y5J1cmC-',
};
