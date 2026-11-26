/**
 * /c/:token → a página normal do site (index.html), já com as tags da prévia do link.
 *
 * O WhatsApp (e quem mais gera prévia) não roda o JavaScript do site: lê só o HTML.
 * Por isso a prévia precisa estar no HTML que sai do servidor. O resto continua igual:
 * o Angular sobe e mostra o convite normalmente.
 *
 * Prévia: com arte → a própria arte (B); sem arte → cartaz no tema, gerado pela API (A).
 */
import { API, dadosDoConvite, quando, type DadosConvite } from './_comum';

export const config = { runtime: 'edge' };

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function tags(c: DadosConvite, url: URL, token: string): string {
  const primeiro = c.convidado_nome.trim().split(/\s+/)[0];
  const local = c.local_nome ? `, ${c.local_nome}` : '';
  // "Convite para Ana" serve para qualquer pessoa (sem errar o gênero)
  const descricao = `Convite para ${primeiro}. ${quando(c.data_hora)}${local}. Confirme pelo link.`;
  // A função recebe a URL já reescrita (/api/convite?token=…); o link público é /c/<token>
  const publico = `${url.origin}/c/${encodeURIComponent(token)}`;
  const temArte = !!c.convite_imagem_url;
  // Sem arte: cartaz no tema, desenhado pela API (backend/app/api/previa.py)
  const imagem = temArte ? c.convite_imagem_url! : `${API}/previa/${encodeURIComponent(token)}.png`;
  const linhas = [
    `<title>${esc(c.evento_nome)}</title>`,
    `<meta name="description" content="${esc(descricao)}">`,
    `<meta property="og:type" content="website">`,
    `<meta property="og:site_name" content="Bora">`,
    `<meta property="og:url" content="${esc(publico)}">`,
    `<meta property="og:title" content="${esc(c.evento_nome)}">`,
    `<meta property="og:description" content="${esc(descricao)}">`,
    `<meta property="og:image" content="${esc(imagem)}">`,
    `<meta property="og:image:alt" content="${esc('Convite: ' + c.evento_nome)}">`,
    ...(temArte ? [] : ['<meta property="og:image:width" content="1200">', '<meta property="og:image:height" content="630">']),
    `<meta name="twitter:card" content="summary_large_image">`,
  ];
  return linhas.join('\n  ');
}

export default async function handler(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const token = url.searchParams.get('token') ?? '';
  const [pagina, convite] = await Promise.all([
    fetch(new URL('/index.html', url.origin)).then((r) => r.text()),
    dadosDoConvite(token),
  ]);

  let html = pagina;
  if (convite) {
    // Troca o título e a descrição genéricos do site pelos do convite
    html = html
      .replace(/<title>[\s\S]*?<\/title>/, '')
      .replace(/<meta name="description"[^>]*>/, '')
      .replace('</head>', `  ${tags(convite, url, token)}\n</head>`);
  }
  return new Response(html, {
    headers: {
      'content-type': 'text/html; charset=utf-8',
      // A página muda pouco; 5 min no cache da Vercel aliviam a API
      'cache-control': 'public, max-age=0, s-maxage=300, stale-while-revalidate=600',
    },
  });
}
