// node --test lex-tests/  (Node >= 22: importa o módulo ESM do datasource)
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  patientNameQuery,
  textWildcardQuery,
  exactQuery,
  stripAccents,
  MIN_WILDCARD_CHARS,
} from '../ohif-viewer/extensions/default/src/DicomWebDataSource/lexQidoFilters.js';

test('LP4: curinga só com 3+ letras', () => {
  assert.equal(MIN_WILDCARD_CHARS, 3);
  assert.equal(patientNameQuery('sil'), '*SIL*');
  assert.equal(patientNameQuery('si'), 'SI');
  assert.equal(patientNameQuery('a'), 'A');
});

test('LP4: sem acento e sem diferenciar maiúsculas', () => {
  assert.equal(patientNameQuery('João'), '*JOAO*');
  assert.equal(patientNameQuery('ÁVILA'), '*AVILA*');
  assert.equal(patientNameQuery('conceição'), '*CONCEICAO*');
  assert.equal(stripAccents('Ñandú'), 'Nandu');
});

test('nome com várias partes vira curinga entre as partes', () => {
  assert.equal(patientNameQuery('  maria   da silva '), '*MARIA*DA*SILVA*');
  assert.equal(patientNameQuery('SILVA^MARIA'), '*SILVA*MARIA*');
});

test('curingas digitados pelo usuário são removidos (sem "listar tudo")', () => {
  assert.equal(patientNameQuery('*'), undefined);
  assert.equal(patientNameQuery('**a?'), 'A');
  assert.equal(patientNameQuery('*si*'), 'SI');
  assert.equal(exactQuery('*'), undefined);
});

test('ID e nº de acesso exatos', () => {
  assert.equal(exactQuery(' SINT-0150 '), 'SINT-0150');
  assert.equal(exactQuery('ACC*'), 'ACC');
  assert.equal(exactQuery(''), undefined);
});

test('sem curinga quando o datasource desliga', () => {
  assert.equal(patientNameQuery('silva', false), 'SILVA');
  assert.equal(textWildcardQuery('torax', false), 'TORAX');
  assert.equal(textWildcardQuery('tórax'), '*TORAX*');
});
