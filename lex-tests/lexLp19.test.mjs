// LP19 (lista padrão por data), UXE1–UXE4 (erro do índice) e polling de "rebuilding" — node --test lex-tests/
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as m from '../ohif-viewer/platform/ui-next/src/components/DataTable/lexWorklistDefaults.js';

const read = p => readFileSync(new URL(`../ohif-viewer/${p}`, import.meta.url), 'utf8');
const wl = read('platform/app/src/routes/WorkList/WorkList.tsx');
const bar = read('platform/app/src/routes/WorkList/WorkListViewBar.tsx');

test('LP19: intervalos no fuso de São Paulo (StudyDate AAAAMMDD)', () => {
  // quarta 28/10/2026 10h em SP
  const qua = new Date('2026-10-28T13:00:00Z');
  assert.deepEqual(m.lexDateRange('hoje', qua), { startDate: '20261028', endDate: '20261028' });
  assert.deepEqual(m.lexDateRange('semana', qua), { startDate: '20261026', endDate: '20261028' });
  assert.deepEqual(m.lexDateRange('semana-passada', qua), { startDate: '20261019', endDate: '20261025' });
  // 28/10 01:30 UTC ainda é 27/10 22:30 em SP
  assert.deepEqual(m.lexDateRange('hoje', new Date('2026-10-28T01:30:00Z')), { startDate: '20261027', endDate: '20261027' });
  // domingo: semana = segunda anterior até o domingo
  assert.deepEqual(m.lexDateRange('semana', new Date('2026-11-01T15:00:00Z')), { startDate: '20261026', endDate: '20261101' });
  // segunda: semana passada atravessa o mês
  assert.deepEqual(m.lexDateRange('semana-passada', new Date('2026-11-02T15:00:00Z')), { startDate: '20261026', endDate: '20261101' });
});

test('LP19: rótulos sem "VISÃO", abre em Hoje', () => {
  assert.deepEqual(m.LEX_DATE_VIEWS.map(v => v.label), ['Hoje', 'Esta semana', 'Semana passada']);
  assert.equal(m.LEX_DEFAULT_VIEW, 'hoje');
  assert.doesNotMatch(bar, /viewLabel|VISÃO|Visão|worklist-views/);
  const sync = read('platform/app/src/hooks/useStudyListStateSync.ts');
  assert.match(sync, /useState<string>\(LEX_DEFAULT_VIEW\)/);
  assert.match(sync, /lexDateRange\(LEX_DEFAULT_VIEW\)/);
  assert.doesNotMatch(wl, /worklist-views/);
});

test('LP19: termo digitado busca em todo o acervo; limpar volta ao filtro', () => {
  const f = [{ id: 'studyDateTime', value: { startDate: '20261028', endDate: '20261028' } }];
  assert.equal(m.lexHasTextSearch(f), false);
  assert.equal(m.lexHasTextSearch([...f, { id: 'patient', value: '  ' }]), false);
  assert.equal(m.lexHasTextSearch([...f, { id: 'patient', value: 'zzteste' }]), true);
  assert.equal(m.lexHasTextSearch([...f, { id: 'mrn', value: '123' }]), true);
  const q = { startDate: '20261028', endDate: '20261028', patientName: 'zzteste', limit: 50 };
  assert.deepEqual(m.lexSearchWholeArchive(q), { patientName: 'zzteste', limit: 50 });
  const semTermo = { startDate: '20261028', endDate: '20261028', limit: 50 };
  assert.deepEqual(m.lexSearchWholeArchive(semTermo), semTermo);
  assert.match(read('platform/app/src/hooks/useStudyListQuery.tsx'), /return lexSearchWholeArchive\(queryFilterValues\)/);
  assert.equal(m.LEX_WHOLE_ARCHIVE_MESSAGE, 'Buscando em todo o acervo');
  assert.match(bar, /disabled=\{inactive\}/);
  assert.match(bar, /role="status"\s*aria-live="polite"[\s\S]{0,120}LEX_WHOLE_ARCHIVE_MESSAGE/);
});

test('LP19: Hoje vazio tem mensagem própria', () => {
  assert.equal(m.LEX_EMPTY_TODAY_MESSAGE, 'Nenhum exame hoje. Veja Esta semana ou digite um nome para buscar em todo o acervo.');
  assert.equal(m.lexEmptyMessageForView('hoje', false), m.LEX_EMPTY_TODAY_MESSAGE);
  assert.equal(m.lexEmptyMessageForView('hoje', true), null);
  assert.equal(m.lexEmptyMessageForView('semana', false), null);
  assert.match(wl, /lexEmptyMessageForView\(activeView, hasTextSearch\)/);
});

test('LP19: menu lateral recolhido; Descrição e Nº de acesso desmarcadas; preferência salva', () => {
  assert.match(wl, /useState\(false\);\s*\/\/ LP19: Descrição/);
  const mem = new Map();
  const st = { getItem: k => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) };
  assert.deepEqual(m.lexInitialColumnVisibility(st), { description: false, accession: false });
  m.lexSaveColumnVisibility(st, { description: true, accession: false, patient: false });
  assert.deepEqual(JSON.parse(mem.get(m.LEX_COLUMNS_PREF_KEY)), { description: true, accession: false });
  assert.deepEqual(m.lexInitialColumnVisibility(st), { description: true, accession: false });
  mem.set(m.LEX_COLUMNS_PREF_KEY, '{quebrado');
  assert.deepEqual(m.lexInitialColumnVisibility(st), { description: false, accession: false });
  assert.match(wl, /initialVisibility=\{initialVisibility\}/);
  assert.match(wl, /onColumnVisibilityChange=\{vis => lexSaveColumnVisibility/);
});

test('UXE1–UXE4: erro do índice sem paginador, alerta único central, botão sem mono, filtros inativos', () => {
  assert.deepEqual(m.lexIndexErrorUi({ status: 'error' }), { hidePagination: true, filtersDisabled: true });
  for (const st of ['ready', 'indexing', 'rebuilding', 'incomplete', undefined]) {
    assert.deepEqual(m.lexIndexErrorUi({ status: st }), { hidePagination: false, filtersDisabled: false });
  }
  const table = read('platform/ui-next/src/components/StudyList/components/Table.tsx');
  assert.match(table, /hidePagination \? null : <DataTable\.Pagination/); // UXE1
  // UXE2: uma ocorrência do alerta, dentro do emptyMessage (centro da tabela), com o botão
  assert.equal((wl.match(/role="alert"/g) || []).length, 1);
  assert.match(wl, /emptyMessage=\{\s*serverPaging && dataIndex\?\.status === 'error' \? \([\s\S]{0,200}role="alert"[\s\S]{0,300}LEX_INDEX_ERROR_MESSAGE[\s\S]{0,100}<LexIndexRetryButton/);
  // UXE3
  assert.doesNotMatch(wl, /lex-num">\{lexRetryLabel/);
  assert.match(wl, /font-sans/);
  assert.match(wl, /<span aria-live="polite">\{lexRetryLabel\(left\)\}<\/span>/);
  // UXE4
  assert.match(table, /disabled=\{filtersDisabled\}/);
  const row = read('platform/ui-next/src/components/DataTable/FilterRow.tsx');
  assert.match(row, /inert/);
  assert.match(row, /aria-disabled=\{disabled \|\| undefined\}/);
  assert.match(wl, /disabled=\{errorUi\.filtersDisabled\}/);
});

test('rebuilding: polling a cada 10 s só do status; para e recarrega ao voltar a ready', async () => {
  assert.equal(m.LEX_INDEX_POLL_MS, 10000);
  assert.equal(m.lexShouldPollIndex('rebuilding'), true);
  for (const st of ['ready', 'indexing', 'error', 'incomplete', undefined]) {
    assert.equal(m.lexShouldPollIndex(st), false);
  }
  let url;
  const ok = async u => { url = u; return { ok: true, json: async () => ({ index: { status: 'ready' } }) }; };
  assert.equal(await m.lexPollIndexStatus(ok), 'ready');
  assert.equal(url, '/clinica-api/worklist/index/status');
  assert.equal(await m.lexPollIndexStatus(async () => ({ ok: false })), null);
  assert.equal(await m.lexPollIndexStatus(async () => { throw new Error('rede'); }), null);
  assert.match(wl, /window\.setInterval\(async \(\) => \{[\s\S]{0,200}lexPollIndexStatus\(\)[\s\S]{0,200}window\.clearInterval\(timer\);[\s\S]{0,80}setIndexStatusOverride\(next\);[\s\S]{0,40}onRefreshRef\.current\(\)/);
  assert.match(wl, /LEX_INDEX_POLL_MS\);/);
  assert.match(wl, /lexShowIndexRebuilding\(\{ status: shownIndexStatus \}\)/);
});
