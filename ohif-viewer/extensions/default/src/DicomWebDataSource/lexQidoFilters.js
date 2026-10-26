/**
 * LEX PACS — normalização dos filtros de texto da lista de estudos (QIDO).
 *
 * - Nome: sem acento, maiúsculo, espaços viram "*"; curinga "*termo*" só com
 *   pelo menos MIN_WILDCARD_CHARS letras/dígitos. Abaixo disso vai exato.
 * - ID do paciente e nº de acesso: sempre exatos (sem curinga).
 * - Curingas digitados pelo usuário ("*", "?", "\") são removidos, para que
 *   "*" sozinho não vire "listar tudo".
 *
 * Observação: o Orthanc compara sem diferenciar maiúsculas, mas NÃO ignora
 * acentos no valor gravado. Tirar o acento da busca acha nomes gravados sem
 * acento (padrão comum em RIS); nomes gravados com acento exigem a busca no
 * servidor (PR de paginação).
 */
export const MIN_WILDCARD_CHARS = 3;

export function stripAccents(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

function cleanText(value) {
  return stripAccents(value)
    .replace(/[*?\\]/g, '')
    .trim()
    .replace(/\s+/g, ' ')
    .toUpperCase();
}

function significantLength(value) {
  return value.replace(/[^A-Z0-9]/g, '').length;
}

export function patientNameQuery(value, useWildcard = true) {
  const text = cleanText(value);
  if (!text) {
    return undefined;
  }
  if (!useWildcard || significantLength(text) < MIN_WILDCARD_CHARS) {
    return text.replace(/ /g, '^');
  }
  return `*${text.replace(/[ ,^]+/g, '*')}*`;
}

export function textWildcardQuery(value, useWildcard = true) {
  const text = cleanText(value);
  if (!text) {
    return undefined;
  }
  if (!useWildcard || significantLength(text) < MIN_WILDCARD_CHARS) {
    return text;
  }
  return `*${text.replace(/ /g, '*')}*`;
}

export function exactQuery(value) {
  const text = String(value ?? '').replace(/[*?\\]/g, '').trim();
  return text || undefined;
}
