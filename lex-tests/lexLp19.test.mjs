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
  assert.match(wl, /onColumnVisibilityChange=\{\(vis, autoHidden\) =>\s+lexSaveColumnVisibility/);
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
  assert.match(wl, /emptyMessage=\{\s*serverPaging && dataIndex\?\.status === 'error' \? \([\s\S]{0,200}role="alert"[\s\S]{0,500}LEX_INDEX_ERROR_MESSAGE[\s\S]{0,100}<LexIndexRetryButton/);
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

test('LP19/UXE: props chegam à tabela (Layout) e coluna desmarcada no início não volta sozinha', () => {
  const layout = read('platform/ui-next/src/components/StudyList/components/Layout.tsx');
  for (const p of ['hidePagination', 'filtersDisabled', 'onColumnVisibilityChange']) {
    assert.match(layout, new RegExp(`${p}=\\{${p}\\}`), p);
  }
  const rc = read('platform/ui-next/src/components/DataTable/useResponsiveColumns.tsx');
  assert.match(rc, /lastColumnVisibilityRef\.current\[sizing\.id\] === false\) \{\s*userHiddenRef\.current\.add\(sizing\.id\)/);
});

test('Lacuna 1: "Limpar filtros" tira o destaque do botão de período', () => {
  const qua = new Date('2026-10-28T13:00:00Z');
  const hoje = [{ id: 'studyDateTime', value: m.lexDateRange('hoje', qua) }];
  const semana = [{ id: 'studyDateTime', value: m.lexDateRange('semana', qua) }];
  // limpar filtros = lista vazia: nenhum período ativo, coerente com o filtro de data removido
  assert.equal(m.lexViewForFilters('hoje', [], qua), m.LEX_NO_VIEW);
  assert.equal(m.lexViewForFilters('semana', [{ id: 'patient', value: '' }], qua), '');
  assert.equal(m.lexIsDateView(m.lexViewForFilters('semana-passada', [], qua)), false);
  // filtro de data igual a uma visão mantém/acha o destaque; data manual diferente não destaca nenhum
  assert.equal(m.lexViewForFilters('hoje', hoje, qua), 'hoje');
  assert.equal(m.lexViewForFilters('', semana, qua), 'semana');
  assert.equal(m.lexViewForFilters('hoje', [{ id: 'studyDateTime', value: { startDate: '20250101', endDate: '20250102' } }], qua), '');
  // a WorkList recalcula o período a cada mudança de filtro (inclui o botão "Limpar filtros")
  assert.match(wl, /setActiveView\(v => lexViewForFilters\(v, next\)\)/);
  const table = read('platform/ui-next/src/components/StudyList/components/Table.tsx');
  assert.match(table, /table\.setColumnFilters\(\[\]\)/);
});

test('Lacuna 2: coluna ocultada pela tela estreita não vira preferência', () => {
  const mem = () => {
    const d = {};
    return { getItem: k => (k in d ? d[k] : null), setItem: (k, v) => { d[k] = String(v); }, d };
  };
  // usuário marcou as duas colunas
  const s = mem();
  m.lexSaveColumnVisibility(s, { description: true, accession: true });
  // tela estreita: o ajuste oculta as duas sozinho → preferência continua true
  m.lexSaveColumnVisibility(s, { description: false, accession: false }, new Set(['description', 'accession']));
  assert.deepEqual(m.lexInitialColumnVisibility(s), { description: true, accession: true });
  // sem preferência salva: o oculto automático não é gravado
  const s2 = mem();
  assert.deepEqual(m.lexSaveColumnVisibility(s2, { description: false }, ['description']), {});
  assert.deepEqual(m.lexInitialColumnVisibility(s2), { description: false, accession: false });
  // escolha explícita do usuário (não automática) continua salva
  m.lexSaveColumnVisibility(s, { description: false, accession: true }, new Set());
  assert.deepEqual(m.lexInitialColumnVisibility(s), { description: false, accession: true });
  // usuário reexibe uma coluna que o ajuste re-oculta: vale o "true" do usuário
  m.lexSaveColumnVisibility(s, { description: true, accession: true }, new Set(['description']));
  assert.equal(m.lexInitialColumnVisibility(s).description, true);
  // fiação: o algoritmo publica as ocultas automáticas e a DataTable as repassa ao salvar
  const rc = read('platform/ui-next/src/components/DataTable/useResponsiveColumns.tsx');
  assert.match(rc, /autoHiddenIdsRef\.current = autoHidden/);
  assert.match(rc, /!userHiddenRef\.current\.has\(id\)/);
  const dt = read('platform/ui-next/src/components/DataTable/DataTable.tsx');
  assert.match(dt, /new Set\(autoHiddenIdsRef\.current\)/);
  assert.match(wl, /lexSaveColumnVisibility\(window\.localStorage, vis, autoHidden\)/);
});

// Contraste WCAG 2.x (luminância relativa)
const lum = hex => {
  const c = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(v => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

test('UXE2 v2: erro do índice como alerta âmbar com ícone e botão com contraste AA', () => {
  const alert = wl.slice(wl.indexOf('data-testid="lex-index-error"') - 200, wl.indexOf('<LexIndexRetryButton\n'));
  assert.match(alert, /role="alert"/);
  assert.match(alert, /style=\{LEX_ALERT_STYLE\}/);
  assert.match(wl, /const LEX_ALERT_STYLE = \{ backgroundColor: '#FFFBEB', borderColor: '#F59E0B', color: '#78350F' \}/);
  assert.match(alert, /<LexAlertIcon \/>/);
  assert.match(wl, /function LexAlertIcon[\s\S]{0,80}<svg\s+aria-hidden="true"\s+data-testid="lex-index-error-icon"/);
  const btn = wl.slice(wl.indexOf('function LexIndexRetryButton'));
  assert.match(btn, /backgroundColor: '#92400E'/);
  assert.match(btn, /'#FFFFFF'/);
  assert.doesNotMatch(btn, /opacity-60/);
  assert.ok(ratio('#FFFFFF', '#92400E') >= 4.5, `botão ${ratio('#FFFFFF', '#92400E')}`);
  assert.ok(ratio('#FEF3C7', '#92400E') >= 4.5, 'botão desabilitado');
  assert.ok(ratio('#78350F', '#FFFBEB') >= 4.5, 'texto do alerta');
  assert.ok(ratio('#B45309', '#FFFBEB') >= 3, 'ícone (não-texto, ≥3:1)');
});

test('vazio de Hoje: "Esta semana" é botão que aplica o período', () => {
  assert.equal(m.LEX_EMPTY_TODAY_PREFIX + 'Esta semana' + m.LEX_EMPTY_TODAY_SUFFIX, m.LEX_EMPTY_TODAY_MESSAGE);
  assert.match(wl, /data-testid="lex-empty-today-semana"[\s\S]{0,200}onClick=\{\(\) => handleViewChange\('semana'\)\}[\s\S]{0,80}Esta semana/);
  assert.match(wl, /<button\s+type="button"\s+data-testid="lex-empty-today-semana"/);
});

test('contador "Exibindo X–Y de N" do topo sem fonte mono', () => {
  const pag = read('platform/ui-next/src/components/DataTable/Pagination.tsx');
  const sp = pag.slice(pag.indexOf('function ServerPagination'));
  const trig = sp.slice(sp.indexOf('<DropdownMenuTrigger'), sp.indexOf('</DropdownMenuTrigger>'));
  assert.doesNotMatch(trig, /lex-num|font-mono/);
  assert.match(trig, /font-sans/);
  assert.match(trig, /tabular-nums/);
  assert.match(trig, /\{range\}/);
});
