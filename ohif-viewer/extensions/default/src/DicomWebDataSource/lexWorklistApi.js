/**
 * LEX PACS — lista de estudos paginada no servidor (portal: POST /clinica-api/worklist/studies).
 *
 * Os filtros (nome, ID, nº de acesso) vão no CORPO da requisição, não na URL do /dicom-web,
 * e o portal faz a comparação sem acento (ver lex-pacs-portal/app/worklist.py).
 * O resultado é o mesmo JSON DICOM do QIDO, então o processResults do OHIF continua valendo.
 */
export const DEFAULT_PAGE_SIZE = 50;
export const MAX_PAGE_SIZE = 200;

function text(value) {
  const v = String(value ?? '').trim();
  return v || undefined;
}

export function buildWorklistBody(params = {}) {
  const limit = Math.min(Math.max(parseInt(params.limit, 10) || DEFAULT_PAGE_SIZE, 1), MAX_PAGE_SIZE);
  const offset = Math.max(parseInt(params.offset, 10) || 0, 0);
  const mods = Array.isArray(params.modalitiesInStudy)
    ? params.modalitiesInStudy
    : params.modalitiesInStudy
      ? String(params.modalitiesInStudy).split(/[,\\]/)
      : [];
  const body = {
    patientName: text(params.patientName),
    patientId: text(params.patientId),
    accessionNumber: text(params.accessionNumber),
    studyDescription: text(params.studyDescription),
    modalitiesInStudy: mods.map(m => String(m).trim()).filter(Boolean),
    startDate: text(params.startDate),
    endDate: text(params.endDate),
    disableWildcard: params.disableWildcard === true,
    limit,
    offset,
  };
  if (!body.modalitiesInStudy.length) {
    delete body.modalitiesInStudy;
  }
  Object.keys(body).forEach(k => body[k] === undefined && delete body[k]);
  return body;
}

/** Converte a resposta do portal em {rows, total, hasMore}. */
export function parseWorklistResponse(payload) {
  const rows = Array.isArray(payload?.studies) ? payload.studies : [];
  const total = Number.isFinite(payload?.total) ? payload.total : null;
  return {
    rows,
    total,
    hasMore: Boolean(payload?.hasMore),
    truncated: Boolean(payload?.truncated),
    sortScope: payload?.sortScope === 'page' ? 'page' : 'global',
    partial: Boolean(payload?.partial),
    index: payload?.index && typeof payload.index === 'object'
      ? {
          status: String(payload.index.status ?? 'ready'),
          indexed: Number(payload.index.indexed) || 0,
          total: Number.isFinite(payload.index.total) ? payload.index.total : null,
          retryInSeconds: Number(payload.index.retryInSeconds) || 0,
        }
      : { status: 'ready', indexed: 0, total: null, retryInSeconds: 0 },
  };
}

export async function fetchWorklistPage(url, params, fetchImpl = fetch) {
  const response = await fetchImpl(url, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(buildWorklistBody(params)),
  });
  if (!response.ok) {
    const err = new Error(`Não foi possível consultar o PACS. Tente de novo. (HTTP ${response.status})`);
    err.status = response.status;
    throw err;
  }
  return parseWorklistResponse(await response.json());
}

/** VW5: nome DICOM para exibição — '^' e ',' viram espaço, sem vírgula sobrando no fim. */
export function lexFormatPN(name) {
  let v = name && typeof name === 'object' ? name.Alphabetic ?? '' : name ?? '';
  if (typeof v !== 'string') {
    v = String(v);
  }
  return v.replace(/[\^,=]+/g, ' ').replace(/\s+/g, ' ').trim();
}
