#!/usr/bin/env bash
# Sincroniza locales/ (fonte única) → viewer OHIF + portal estático.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/locales"
OHIF_LOCALES="${ROOT}/ohif-viewer/platform/i18n/src/locales"
PORTAL_LOCALES="${ROOT}/lex-pacs-portal/static/locales"
LANGS=(pt-BR en-US es)

if [ ! -d "$SRC" ]; then
  echo "Pasta locales/ não encontrada em ${ROOT}" >&2
  exit 1
fi

for lang in "${LANGS[@]}"; do
  if [ ! -d "${SRC}/${lang}" ]; then
    echo "Idioma ausente: ${SRC}/${lang}" >&2
    exit 1
  fi

  # Viewer: namespace LexPacs
  if [ -f "${SRC}/${lang}/LexPacs.json" ]; then
    mkdir -p "${OHIF_LOCALES}/${lang}"
    cp "${SRC}/${lang}/LexPacs.json" "${OHIF_LOCALES}/${lang}/LexPacs.json"
  fi

  # Portal: Portal + ClinicalLogin
  mkdir -p "${PORTAL_LOCALES}/${lang}"
  for ns in Portal ClinicalLogin; do
    if [ -f "${SRC}/${lang}/${ns}.json" ]; then
      cp "${SRC}/${lang}/${ns}.json" "${PORTAL_LOCALES}/${lang}/${ns}.json"
    fi
  done
done

echo "Regenerando índices OHIF i18n…"
node "${ROOT}/ohif-viewer/platform/i18n/writeLocaleIndexFiles.js"

echo "Locales sincronizados:"
echo "  OHIF:  ${OHIF_LOCALES}/{pt-BR,en-US,es}/LexPacs.json"
echo "  Portal: ${PORTAL_LOCALES}/{pt-BR,en-US,es}/"
