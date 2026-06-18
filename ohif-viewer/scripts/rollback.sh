#!/usr/bin/env bash
# Volta LEX PACS para uma versão anterior (E6 rollback).
#
# Uso:
#   ./scripts/rollback.sh 0.4.0
#   ./scripts/rollback.sh 0.4.0 /caminho/backup/2026-06-18_120000
#
# Os volumes Docker permanecem intactos; use restore-backup.sh se precisar
# recuperar dados de um snapshot anterior.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VERSION_FILE="${PROJECT_DIR}/LEX_PACS_VERSION"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

TARGET_VERSION="${1:-}"
BACKUP_SNAPSHOT="${2:-}"

if [ -z "${TARGET_VERSION}" ]; then
  echo "Uso: $0 <versão-anterior> [diretório-de-backup]" >&2
  exit 1
fi

cd "${PROJECT_DIR}"

CURRENT_VERSION="unknown"
if [ -f "${VERSION_FILE}" ]; then
  CURRENT_VERSION="$(tr -d '[:space:]' < "${VERSION_FILE}")"
fi

if [ -n "${BACKUP_SNAPSHOT}" ]; then
  echo "▶ Restore de volumes a partir de ${BACKUP_SNAPSHOT}"
  "${SCRIPT_DIR}/restore-backup.sh" "${BACKUP_SNAPSHOT}"
fi

echo "▶ Rollback de imagens: ${CURRENT_VERSION} → ${TARGET_VERSION}"
echo "${TARGET_VERSION}" > "${VERSION_FILE}"
export LEX_PACS_VERSION="${TARGET_VERSION}"

docker compose -f "${COMPOSE_FILE}" build
docker compose -f "${COMPOSE_FILE}" up -d

echo "▶ Smoke test pós-rollback"
"${SCRIPT_DIR}/smoke-test.sh"

echo
echo "Rollback concluído: ${CURRENT_VERSION} → ${TARGET_VERSION}"
