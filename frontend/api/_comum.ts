/** Partes comuns às funções da prévia do link (arquivos com "_" não viram rota na Vercel). */

/** API do Bora. Na Vercel pode ser trocada pela variável BORA_API_URL (ex.: testes). */
export const API = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
  ?.BORA_API_URL ?? 'https://api.147-15-82-161.sslip.io';

export interface DadosConvite {
  convidado_nome: string;
  evento_nome: string;
  data_hora: string;
  local_nome: string | null;
  convite_imagem_url: string | null;
}

export async function dadosDoConvite(token: string): Promise<DadosConvite | null> {
  if (!/^[\w-]{4,100}$/.test(token)) return null;
  try {
    const r = await fetch(`${API}/convites/${token}`, { headers: { accept: 'application/json' } });
    return r.ok ? ((await r.json()) as DadosConvite) : null;
  } catch {
    return null; // API fora do ar: a página abre do mesmo jeito, só sem prévia
  }
}

/** "Sábado, 16 de janeiro, 15h" (ou "15h30") no horário de Brasília. */
export function quando(iso: string): string {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat('pt-BR', {
      timeZone: 'America/Sao_Paulo',
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    })
      .formatToParts(new Date(iso))
      .map((x) => [x.type, x.value]),
  );
  const hora = `${Number(p['hour'])}h${p['minute'] === '00' ? '' : p['minute']}`;
  // "quarta-feira" → "Quarta", igual ao cartaz (backend/app/domain/cartaz.py)
  const semana = p['weekday'].replace(/-feira$/, '');
  const dia = semana.charAt(0).toUpperCase() + semana.slice(1);
  return `${dia}, ${p['day']} de ${p['month']}, ${hora}`;
}
