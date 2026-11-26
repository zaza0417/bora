/**
 * Temas do convite. As cores e fontes de cada um ficam em convite.scss ([data-tema]) e
 * no cartaz da prévia do link (frontend/api/og.ts); aqui ficam o nome e o tom do texto.
 */
export type Tema = 'FESTA' | 'NOITE' | 'CASAMENTO' | 'INFANTIL';

export interface InfoTema {
  id: Tema;
  nome: string;
  descricao: string;
  /** Pergunta no topo do cartão de resposta. */
  pergunta: string;
  /** Texto do botão de confirmar. */
  vou: string;
}

export const TEMAS: InfoTema[] = [
  { id: 'FESTA', nome: 'Festa', descricao: 'Amarelo, o jeito Bora', pergunta: 'E aí, bora?', vou: 'Vou!' },
  { id: 'NOITE', nome: 'Noite', descricao: 'Escuro com dourado', pergunta: 'Vai brindar com a gente?', vou: 'Vou!' },
  { id: 'CASAMENTO', nome: 'Casamento', descricao: 'Creme, letra serifada', pergunta: 'Confirme sua presença', vou: 'Vou' },
  { id: 'INFANTIL', nome: 'Infantil', descricao: 'Cores vivas, tudo redondo', pergunta: 'Vem brincar?', vou: 'Vou!' },
];

export function infoTema(tema: string | null | undefined): InfoTema {
  return TEMAS.find((t) => t.id === tema) ?? TEMAS[0];
}
