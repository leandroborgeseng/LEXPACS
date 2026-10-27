// Paginação no servidor (LP1–LP4) e LX6 — node --test lex-tests/
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  buildWorklistBody,
  parseWorklistResponse,
  fetchWorklistPage,
} from '../ohif-viewer/extensions/default/src/DicomWebDataSource/lexWorklistApi.js';
import {
  lexPageRange,
  lexPageCount,
  lexPageOf,
} from '../ohif-viewer/platform/ui-next/src/components/DataTable/lexPaginationLabel.js';

const read = p => readFileSync(new URL(`../ohif-viewer/${p}`, import.meta.url), 'utf8');

test('corpo da busca: limit/offset no servidor, nada de lista fixa de 100', () => {
  const b = buildWorklistBody({ patientName: ' josé ', limit: 50, offset: 100, modalitiesInStudy: ['CT', ''] });
  assert.deepEqual(b, { patientName: 'josé', modalitiesInStudy: ['CT'], disableWildcard: false, limit: 50, offset: 100 });
  assert.equal(buildWorklistBody({ limit: 5000 }).limit, 200);
  assert.equal(buildWorklistBody({}).limit, 50);
  assert.equal(buildWorklistBody({ offset: -3 }).offset, 0);
});

test('LP9: nome e ID vão no corpo do POST, nunca na URL', async () => {
  let seen;
  const fake = async (url, init) => {
    seen = { url, init };
    return { ok: true, json: async () => ({ studies: [{}], total: 35214, hasMore: true }) };
  };
  const r = await fetchWorklistPage('/clinica-api/worklist/studies', { patientName: 'Conceição', patientId: 'SINT-1' }, fake);
  assert.equal(seen.url, '/clinica-api/worklist/studies');
  assert.equal(seen.init.method, 'POST');
  assert.match(seen.init.body, /Concei/);
  assert.doesNotMatch(seen.url, /Concei|SINT/);
  assert.deepEqual(r, { rows: [{}], total: 35214, hasMore: true, truncated: false, sortScope: 'global', partial: false, index: { status: 'ready', indexed: 0, total: null, retryInSeconds: 0 } });
});

test('erro do PACS vira mensagem com código HTTP', async () => {
  const fake = async () => ({ ok: false, status: 502 });
  await assert.rejects(fetchWorklistPage('/x', {}, fake), /HTTP 502/);
});

test('resposta sem total: total null', () => {
  assert.deepEqual(parseWorklistResponse({ studies: [], hasMore: true }), { rows: [], total: null, hasMore: true, truncated: false, sortScope: 'global', partial: false, index: { status: 'ready', indexed: 0, total: null, retryInSeconds: 0 } });
});

test('textos da paginação (esboço do Designer)', () => {
  assert.equal(lexPageRange({ pageIndex: 0, pageSize: 50, count: 50, total: 35214 }), 'Exibindo 1–50 de 35.214 exames');
  assert.equal(lexPageRange({ pageIndex: 2, pageSize: 50, count: 50, total: null }), 'Exibindo 101–150');
  assert.equal(lexPageOf({ pageIndex: 2, pageSize: 50, total: 35214 }), 'Página 3 de 705');
  assert.equal(lexPageOf({ pageIndex: 2, pageSize: 50, total: null }), null);
  assert.equal(lexPageCount({ pageIndex: 2, pageSize: 50, total: null, hasMore: true }), 4);
  assert.equal(lexPageCount({ pageIndex: 2, pageSize: 50, total: null, hasMore: false }), 3);
  assert.equal(lexPageCount({ pageSize: 50, total: 35214 }), 705);
  assert.equal(lexPageRange({ count: 0, total: 0 }), 'Nenhum exame');
});

test('LX6: números da lista com .lex-num (Plex Mono tnum no claro)', () => {
  const cols = read('platform/ui-next/src/components/StudyList/columns/defaultColumns.tsx');
  for (const id of ['MRN', 'STUDY_DATE_TIME', 'ACCESSION', 'INSTANCES']) {
    const block = cols.slice(cols.indexOf(`id: COLUMN_IDS.${id}`));
    const cell = block.slice(block.indexOf('cell:'), block.indexOf('cell:') + 400);
    assert.match(cell, /lex-num/, id);
  }
  assert.match(read('platform/ui-next/src/components/DataTable/Pagination.tsx'), /lex-num/);
  const css = read('platform/ui-next/src/tailwind.css');
  assert.match(css, /\[data-theme='light'\] \.lex-num \{\s*font-family: 'IBM Plex Mono'[^}]*tabular-nums/);
});

test('config: lista usa a API paginada e mantém curinga e queryLimit', () => {
  const cfg = read('platform/app/public/config/default.js');
  assert.match(cfg, /lexWorklistApi: '\/clinica-api\/worklist\/studies'/);
  assert.match(cfg, /supportsWildcard: true/);
});

test('VW5: nome sem ^ nem vírgula sobrando', async () => {
  const { lexFormatPN } = await import('../ohif-viewer/extensions/default/src/DicomWebDataSource/lexWorklistApi.js');
  assert.equal(lexFormatPN({ Alphabetic: 'CONCEIÇÃO^JOSÉ^^' }), 'CONCEIÇÃO JOSÉ');
  assert.equal(lexFormatPN('SILVA^ANA'), 'SILVA ANA');
  assert.equal(lexFormatPN(undefined), '');
});

test('VW3/VW4: data dd/mm/aaaa HH:mm e textos pt-BR', () => {
  const j = p => JSON.parse(read(`platform/i18n/src/locales/pt-BR/${p}`));
  assert.equal(j('Common.json').localDateFormat, 'DD/MM/YYYY');
  assert.equal(j('Common.json').localTimeFormat, 'HH:mm');
  assert.equal(j('StudyList.json').SelectStudy, 'Selecione um exame');
  assert.equal(j('StudyList.json').LaunchWorkflow, 'Abrir no visualizador');
  assert.equal(j('DatePicker.json').Start, 'Data inicial');
  assert.equal(j('DataTable.json').View, 'Exibição');
  assert.match(read('platform/app/public/html-templates/index.html'), /<title>PACS PMF<\/title>/);
});

test('LP9: texto da busca fora da URL do navegador', () => {
  const sync = read('platform/app/src/hooks/useStudyListStateSync.ts');
  assert.match(sync, /lexText\[urlKeyForTextFilter\(filter\.id\)\] = filter\.value/);
  assert.doesNotMatch(sync, /query\[urlKeyForTextFilter/);
});

test('duplo clique abre o visualizador básico, sem seletor de workflow', async () => {
  const { lexDoubleClickWorkflow } = await import('../ohif-viewer/platform/ui-next/src/components/StudyList/components/lexDoubleClick.js');
  const seg = { id: '@ohif/mode-segmentation' };
  const basic = { id: '@ohif/mode-longitudinal' };
  assert.equal(lexDoubleClickWorkflow([seg, basic]), basic);
  assert.equal(lexDoubleClickWorkflow([seg]), undefined);
  const fixo = { id: '@ohif/mode-tmtv', isDefault: true };
  assert.equal(lexDoubleClickWorkflow([basic, fixo]), fixo);
  const table = read('platform/ui-next/src/components/StudyList/components/Table.tsx');
  assert.match(table, /lexDoubleClickWorkflow\(getWorkflowsForStudy\(original\)\)/);
  assert.match(table, /onDoubleClick: row => openRow\(row\)/);
});

test('VW11b/d: Enter abre; segundo duplo clique ignorado; "Abrindo exame…"', () => {
  const table = read('platform/ui-next/src/components/StudyList/components/Table.tsx');
  assert.match(table, /event\.key === 'Enter'[\s\S]{0,80}openRow\(row\)/);
  assert.match(table, /if \(openingId\) \{\s*return;/);
  assert.match(table, /Abrindo exame…/);
  assert.match(read('platform/ui-next/src/components/DataTable/DataTable.tsx'), /tabIndex: 0,\s*onKeyDown/);
});

test('"Buscando…" só depois de 1 s, com filtros visíveis', async () => {
  const m = await import('../ohif-viewer/platform/ui-next/src/components/DataTable/lexPaginationLabel.js');
  assert.equal(m.LEX_SEARCHING_DELAY_MS, 1000);
  assert.equal(m.lexShowSearching(true, 999), false);
  assert.equal(m.lexShowSearching(true, 1000), true);
  assert.equal(m.lexShowSearching(false, 5000), false);
  const wl = read('platform/app/src/routes/WorkList/WorkList.tsx');
  assert.match(wl, /setTimeout\([\s\S]{0,120}LEX_SEARCHING_DELAY_MS/);
  // o aviso fica junto da barra de filtros (toolbarBelowComponent), que continua renderizada
  assert.match(wl, /<WorkListViewBar[\s\S]{0,1200}searchingSlow \?[\s\S]{0,400}Buscando…/);
  assert.equal(m.lexSortNote('global'), null);
});

test('índice preparando: mensagem com X de N, parcial e nunca "Nenhum exame encontrado"', async () => {
  const m = await import('../ohif-viewer/platform/ui-next/src/components/DataTable/lexPaginationLabel.js');
  assert.equal(m.lexIndexingMessage({ indexed: 1000, total: 3000 }), 'Preparando a busca no acervo… 1.000 de 3.000 exames indexados');
  assert.equal(m.lexIndexingMessage({ indexed: 0, total: null }), 'Preparando a busca no acervo… 0 exames indexados');
  const { parseWorklistResponse } = await import('../ohif-viewer/extensions/default/src/DicomWebDataSource/lexWorklistApi.js');
  const r = parseWorklistResponse({ studies: [], total: 0, partial: true, index: { status: 'indexing', indexed: 10, total: 20 } });
  assert.equal(r.partial, true);
  assert.deepEqual(r.index, { status: 'indexing', indexed: 10, total: 20, retryInSeconds: 0 });
  const wl = read('platform/app/src/routes/WorkList/WorkList.tsx');
  assert.match(wl, /serverPaging && dataPartial\s*\?\s*lexIndexingMessage\(dataIndex\)/);
  assert.match(wl, /resultados parciais/);
  const q = read('platform/app/src/hooks/useStudyListQuery.tsx');
  assert.match(q, /if \(!data\.partial \|\| isLoading\)/);
  assert.match(q, /LEX_INDEX_POLL_MS = 3000/);
});

test('carga falhou: mensagem do Designer, botão com intervalo de 60 s, "Busca no acervo indisponível", sem reconsulta a cada 3 s', async () => {
  const m = await import('../ohif-viewer/platform/ui-next/src/components/DataTable/lexPaginationLabel.js');
  assert.equal(m.LEX_INDEX_ERROR_MESSAGE, 'Busca no acervo indisponível no momento. Tente novamente em alguns minutos.');
  assert.equal(m.lexRetryLabel(42), 'Tentar de novo em 42 s');
  assert.equal(m.lexRetryLabel(0), 'Tentar de novo');
  assert.match(read('platform/app/src/routes/WorkList/WorkList.tsx'), /disabled=\{busy \|\| left > 0\}[\s\S]{0,300}lexRetryLabel\(left\)/);
  const { parseWorklistResponse } = await import('../ohif-viewer/extensions/default/src/DicomWebDataSource/lexWorklistApi.js');
  const r = parseWorklistResponse({ studies: [], total: 0, partial: false, index: { status: 'error', indexed: 0, total: null } });
  assert.equal(r.partial, false);
  assert.equal(r.index.status, 'error');
  const wl = read('platform/app/src/routes/WorkList/WorkList.tsx');
  assert.match(wl, /dataIndex\?\.status === 'error'[\s\S]{0,200}LEX_INDEX_ERROR_MESSAGE/);
  // a reconsulta só existe para resultado parcial; error chega com partial false
  assert.match(read('platform/app/src/hooks/useStudyListQuery.tsx'), /if \(!data\.partial \|\| isLoading\)/);
});

test('StudyList.Table (Layout) repassa paginação no servidor, banners e mensagem de vazio', () => {
  const src = read('platform/ui-next/src/components/StudyList/components/Layout.tsx');
  for (const prop of ['manualPagination', 'rowCount', 'hasMore', 'sortNote', 'emptyMessage', 'toolbarBelowComponent']) {
    assert.match(src, new RegExp(`${prop}=\\{${prop}\\}`), prop);
  }
});

test('#9 ressalva 3: aviso não bloqueante quando o índice está incomplete', async () => {
  const m = await import('../ohif-viewer/platform/ui-next/src/components/DataTable/lexPaginationLabel.js');
  assert.equal(m.LEX_INDEX_INCOMPLETE_MESSAGE, 'Índice em atualização: alguns exames podem ainda não aparecer.');
  assert.equal(m.lexShowIndexIncomplete({ status: 'incomplete' }), true);
  for (const st of ['ready', 'indexing', 'error', undefined]) {
    assert.equal(m.lexShowIndexIncomplete({ status: st }), false);
  }
  assert.equal(m.lexShowIndexIncomplete(null), false);
  const wl = read('platform/app/src/routes/WorkList/WorkList.tsx');
  // aria-live, role=status (não alert) e a lista continua renderizada (não é emptyMessage)
  assert.match(wl, /lexShowIndexIncomplete\(dataIndex\) \? \(\s*<div\s*role="status"\s*aria-live="polite"/);
  assert.match(wl, /\{LEX_INDEX_INCOMPLETE_MESSAGE\}/);
  assert.doesNotMatch(wl, /emptyMessage=\{[^}]*INCOMPLETE/);
});
