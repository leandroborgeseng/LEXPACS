#!/usr/bin/env sh
# Valida integridade de um snapshot de backup (E5) sem restaurar volumes.
set -eu

SNAPSHOT="${1:-}"
if [ -z "${SNAPSHOT}" ] || [ ! -d "${SNAPSHOT}" ]; then
  echo "Uso: $0 <diretório-do-backup>" >&2
  exit 1
fi

errors=0

if [ ! -f "${SNAPSHOT}/manifest.json" ]; then
  echo "✗ manifest.json ausente" >&2
  errors=$((errors + 1))
else
  python3 -c "import json,sys; json.load(open('${SNAPSHOT}/manifest.json'))" \
    && echo "✓ manifest.json válido" || { echo "✗ manifest.json inválido" >&2; errors=$((errors + 1)); }
fi

found_archive=0
for archive in "${SNAPSHOT}"/*.tar.gz; do
  [ -f "${archive}" ] || continue
  found_archive=1
  if tar tzf "${archive}" >/dev/null 2>&1; then
    echo "✓ $(basename "${archive}") íntegro"
  else
    echo "✗ $(basename "${archive}") corrompido" >&2
    errors=$((errors + 1))
  fi
done

if [ "${found_archive}" -eq 0 ]; then
  echo "✗ nenhum .tar.gz encontrado" >&2
  errors=$((errors + 1))
fi

if [ -f "${SNAPSHOT}/postgres.dump" ]; then
  if head -c 5 "${SNAPSHOT}/postgres.dump" | grep -q 'PGDMP\|--'; then
    echo "✓ postgres.dump presente"
  else
    echo "✓ postgres.dump presente (formato não verificado)"
  fi
else
  echo "○ postgres.dump ausente (opcional se postgres indisponível)"
fi

exit "${errors}"
