// LD1/LD4: filtro do painel lexReport no layout (modes/basic/src/lexLaudos.ts).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const src = readFileSync(new URL('../ohif-viewer/modes/basic/src/lexLaudos.ts', import.meta.url), 'utf8');
// Remove as anotações de tipo (TS mínimo) e carrega como módulo JS.
const js = src
  .replace(/applyLaudosVisibility<[^(]*\(/, 'applyLaudosVisibility(')
  .replace(/\(\s*layout: T\s*\): Promise<T>/, '(layout)')
  .replace(/\): Promise<boolean>/g, ')')
  .replace(/\(panels: string\[\] = \[\], visivel: boolean\): string\[\]/, '(panels = [], visivel)');
const mod = await import('data:text/javascript,' + encodeURIComponent(js));
const PANEL = mod.LEX_REPORT_PANEL_ID;
const layout = () => ({ props: { rightPanels: [PANEL, 'seg', 'meas'] } });

const semAba = [
  ['flag desligada (admin)', async () => ({ ok: true, json: async () => ({ laudos_visivel: false, permissions: { is_admin: true, can_sign: true } }) })],
  ['campo ausente', async () => ({ ok: true, json: async () => ({ permissions: { can_sign: true } }) })],
  ['sem sessão (401)', async () => ({ ok: false, json: async () => ({}) })],
  ['erro de rede', async () => { throw new Error('rede'); }],
  ['valor não booleano', async () => ({ ok: true, json: async () => ({ laudos_visivel: 'true' }) })],
];
for (const [nome, impl] of semAba) {
  test(`LD1: sem aba Laudos — ${nome}`, async () => {
    globalThis.fetch = impl;
    const out = await mod.applyLaudosVisibility(layout());
    assert.deepEqual(out.props.rightPanels, ['seg', 'meas']);
  });
}

test('LD4: aba Laudos só com laudos_visivel === true', async () => {
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ laudos_visivel: true }) });
  const out = await mod.applyLaudosVisibility(layout());
  assert.deepEqual(out.props.rightPanels, [PANEL, 'seg', 'meas']);
});

test('LD1: modos com lexReport passam pelo filtro e o painel se esconde sozinho', () => {
  const read = p => readFileSync(new URL(`../ohif-viewer/${p}`, import.meta.url), 'utf8');
  assert.match(read('modes/basic/src/index.tsx'), /return applyLaudosVisibility\(structuredCloneWithFunctions\(this\.layoutInstance\)\)/);
  const longi = read('modes/longitudinal/src/index.ts');
  assert.match(longi, /\.\.\.basicRoute/);
  assert.doesNotMatch(longi, /layoutTemplate\s*[:(]/);
  assert.match(read('extensions/default/src/Panels/PanelLexReport.tsx'), /if \(!laudosVisivel\) \{\s*return null;/);
});
