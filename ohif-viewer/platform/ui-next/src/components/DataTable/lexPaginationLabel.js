/**
 * LEX PACS — texto da paginação no servidor (busca-paginada-esboco.md):
 *   "Exibindo 1–50 de 35.214 exames" e "Página 3 de 705"; sem total: só "Exibindo 101–150".
 */
const fmt = n => Number(n).toLocaleString('pt-BR');

export function lexPageRange({ pageIndex = 0, pageSize = 50, count = 0, total = null }) {
  if (!count) {
    return total === 0 || total === null ? 'Nenhum exame' : `Exibindo 0 de ${fmt(total)} exames`;
  }
  const start = pageIndex * pageSize + 1;
  const end = pageIndex * pageSize + count;
  const range = `Exibindo ${fmt(start)}–${fmt(end)}`;
  return total === null || total === undefined ? range : `${range} de ${fmt(total)} exames`;
}

export function lexPageCount({ pageIndex = 0, pageSize = 50, total = null, hasMore = false }) {
  if (total === null || total === undefined) {
    return hasMore ? pageIndex + 2 : pageIndex + 1;
  }
  return Math.max(1, Math.ceil(total / pageSize));
}

export function lexPageOf({ pageIndex = 0, pageSize = 50, total = null }) {
  if (total === null || total === undefined) {
    return null;
  }
  return `Página ${fmt(pageIndex + 1)} de ${fmt(Math.max(1, Math.ceil(total / pageSize)))}`;
}
