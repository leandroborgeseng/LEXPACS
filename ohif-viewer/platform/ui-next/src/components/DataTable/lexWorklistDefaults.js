/**
 * LEX PACS — LP19 (lista padrão por data) e UXE1–UXE4 (estado de erro do índice).
 * Lógica pura (sem React), testada em lex-tests/lexLp19.test.mjs.
 */

export const LEX_TZ = 'America/Sao_Paulo';

/** Data de hoje no fuso de São Paulo, como {y, m, d} (m de 1 a 12). */
export function lexTodayParts(now = new Date()) {
  const s = new Intl.DateTimeFormat('en-CA', {
    timeZone: LEX_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now); // AAAA-MM-DD
  const [y, m, d] = s.split('-').map(Number);
  return { y, m, d };
}

const pad = n => String(n).padStart(2, '0');
/** Data de calendário (sem fuso: usa UTC só como aritmética de dias) para AAAAMMDD. */
const ymd = dt => `${dt.getUTCFullYear()}${pad(dt.getUTCMonth() + 1)}${pad(dt.getUTCDate())}`;
const addDays = (dt, n) => new Date(dt.getTime() + n * 86400000);

/**
 * Intervalo AAAAMMDD de cada visão, comparado com o StudyDate do exame:
 * hoje = só hoje; semana = segunda desta semana até hoje; semana-passada = segunda a domingo anteriores.
 */
export function lexDateRange(viewId, now = new Date()) {
  const { y, m, d } = lexTodayParts(now);
  const today = new Date(Date.UTC(y, m - 1, d));
  const sinceMonday = (today.getUTCDay() + 6) % 7; // segunda = 0
  const monday = addDays(today, -sinceMonday);
  if (viewId === 'semana') {
    return { startDate: ymd(monday), endDate: ymd(today) };
  }
  if (viewId === 'semana-passada') {
    return { startDate: ymd(addDays(monday, -7)), endDate: ymd(addDays(monday, -1)) };
  }
  return { startDate: ymd(today), endDate: ymd(today) };
}

/** Rótulos sem "VISÃO" (LP19). A lista sempre abre em Hoje. */
export const LEX_DATE_VIEWS = [
  { id: 'hoje', label: 'Hoje' },
  { id: 'semana', label: 'Esta semana' },
  { id: 'semana-passada', label: 'Semana passada' },
];
export const LEX_DEFAULT_VIEW = 'hoje';

/** Nenhum botão de período ativo (ex.: depois de "Limpar filtros"). */
export const LEX_NO_VIEW = '';

/**
 * Botão de período que deve ficar destacado para os filtros atuais.
 * Sem filtro de data (ex.: "Limpar filtros") → nenhum; intervalo igual ao de uma visão → essa visão
 * (preferindo a atual); intervalo manual diferente → nenhum.
 */
export function lexViewForFilters(currentView, filters, now = new Date(), dateId = 'studyDateTime') {
  const f = (filters || []).find(x => x?.id === dateId);
  const v = f?.value;
  if (!v || typeof v !== 'object' || (!v.startDate && !v.endDate)) {
    return LEX_NO_VIEW;
  }
  const same = id => {
    const r = lexDateRange(id, now);
    return r.startDate === v.startDate && r.endDate === v.endDate;
  };
  if (lexIsDateView(currentView) && same(currentView)) {
    return currentView;
  }
  return LEX_DATE_VIEWS.find(x => same(x.id))?.id ?? LEX_NO_VIEW;
}

export function lexIsDateView(id) {
  return LEX_DATE_VIEWS.some(v => v.id === id);
}

/** Algum filtro de texto (nome, prontuário, nº de acesso, descrição) com termo digitado? */
export function lexHasTextSearch(filters, textIds = ['patient', 'mrn', 'accession', 'description']) {
  return (filters || []).some(
    f => textIds.includes(f?.id) && typeof f.value === 'string' && f.value.trim() !== ''
  );
}

/** Mesma regra no lado da consulta (parâmetros já resolvidos): com termo, busca em todo o acervo. */
export function lexSearchWholeArchive(values) {
  const v = { ...(values || {}) };
  const hasText = ['patientName', 'patientId', 'accessionNumber', 'studyDescription'].some(
    k => typeof v[k] === 'string' && v[k].trim() !== ''
  );
  if (hasText) {
    delete v.startDate;
    delete v.endDate;
  }
  return v;
}

export const LEX_WHOLE_ARCHIVE_PLACEHOLDER = 'Todo o acervo';

/**
 * Virada do dia: o filtro de data do período ativo está defasado em relação a `now` (SP)?
 * Usado ao voltar o foco para a aba (aba aberta antes da meia-noite).
 */
export function lexViewRangeIsStale(viewId, filters, now = new Date()) {
  if (!LEX_DATE_VIEWS.some(v => v.id === viewId) || lexHasTextSearch(filters)) {
    return false;
  }
  const want = lexDateRange(viewId, now);
  if (!want) {
    return false;
  }
  const cur = (filters || []).find(f => f && f.id === 'studyDateTime')?.value;
  return !cur || cur.startDate !== want.startDate || cur.endDate !== want.endDate;
}

export const LEX_WHOLE_ARCHIVE_MESSAGE = 'Buscando em todo o acervo';
export const LEX_EMPTY_TODAY_MESSAGE =
  'Nenhum exame hoje. Veja Esta semana ou digite um nome para buscar em todo o acervo.';

export const LEX_EMPTY_TODAY_PREFIX = 'Nenhum exame hoje. Veja ';
export const LEX_EMPTY_TODAY_SUFFIX = ' ou digite um nome para buscar em todo o acervo.';

export function lexEmptyMessageForView(viewId, hasTextSearch) {
  return viewId === 'hoje' && !hasTextSearch ? LEX_EMPTY_TODAY_MESSAGE : null;
}

/** Colunas padrão: Descrição e Nº de acesso desmarcadas; a escolha do usuário fica salva. */
export const LEX_COLUMNS_PREF_KEY = 'lex.worklist.columns';
export const LEX_PREF_COLUMN_IDS = ['description', 'accession'];

export function lexInitialColumnVisibility(storage) {
  const vis = { description: false, accession: false };
  try {
    const saved = JSON.parse(storage?.getItem(LEX_COLUMNS_PREF_KEY) || 'null');
    if (saved && typeof saved === 'object') {
      LEX_PREF_COLUMN_IDS.forEach(id => {
        if (typeof saved[id] === 'boolean') {
          vis[id] = saved[id];
        }
      });
    }
  } catch {
    /* preferência corrompida: usa o padrão */
  }
  return vis;
}

/**
 * Salva só a escolha explícita do usuário. `autoHiddenIds` = colunas que o ajuste de tela estreita
 * ocultou sozinho: o "oculto" automático não é gravado (mantém o valor já salvo, ou nada).
 */
export function lexSaveColumnVisibility(storage, visibility, autoHiddenIds) {
  const auto = autoHiddenIds instanceof Set ? autoHiddenIds : new Set(autoHiddenIds || []);
  let saved = {};
  try {
    saved = JSON.parse(storage?.getItem(LEX_COLUMNS_PREF_KEY) || 'null') || {};
  } catch {
    saved = {};
  }
  const pref = {};
  LEX_PREF_COLUMN_IDS.forEach(id => {
    if (auto.has(id) && visibility?.[id] === false) {
      if (typeof saved[id] === 'boolean') {
        pref[id] = saved[id];
      }
    } else if (typeof visibility?.[id] === 'boolean') {
      pref[id] = visibility[id];
    }
  });
  try {
    storage?.setItem(LEX_COLUMNS_PREF_KEY, JSON.stringify(pref));
  } catch {
    /* sem storage: só não salva */
  }
  return pref;
}

/** UXE1/UXE4: no erro do índice, sem paginador e com filtros desativados. */
export function lexIndexErrorUi(index) {
  const error = index?.status === 'error';
  return { hidePagination: error, filtersDisabled: error };
}

/** Enquanto o índice estiver em "rebuilding", a tela consulta o status a cada 10 s. */
export const LEX_INDEX_POLL_MS = 10000;
export const LEX_INDEX_STATUS_URL = '/clinica-api/worklist/index/status';

export function lexShouldPollIndex(status) {
  return status === 'rebuilding';
}

/**
 * Uma rodada do polling: devolve o status novo (ou null em falha de rede, que mantém o polling).
 * Quando sai de "rebuilding", quem chama para de consultar e recarrega a lista.
 */
export async function lexPollIndexStatus(fetchImpl = fetch) {
  try {
    const r = await fetchImpl(LEX_INDEX_STATUS_URL, { credentials: 'include' });
    if (!r.ok) {
      return null;
    }
    const body = await r.json();
    return typeof body?.index?.status === 'string' ? body.index.status : null;
  } catch {
    return null;
  }
}
