#!/usr/bin/env bash
# Atualiza LEX PACS para uma nova versão (E6).
#
# Uso:
#   ./scripts/upgrade.sh 0.4.1
#   SKIP_BACKUP=1 ./scripts/upgrade.sh 0.4.1   # só desenvolvimento
#
# Fluxo: backup → atualiza LEX_PACS_VERSION → rebuild → smoke test

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VERSION_FILE="${PROJECT_DIR}/LEX_PACS_VERSION"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

NEW_VERSION="${1:-}"
if [ -z "${NEW_VERSION}" ]; then
  echo "Uso: $0 <nova-versão>" >&2
  echo "Ex.: $0 0.4.1" >&2
  exit 1
fi

if ! echo "${NEW_VERSION}" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$'; then
  echo "Versão inválida: ${NEW_VERSION} (use semver, ex. 0.4.1)" >&2
  exit 1
fi

CURRENT_VERSION="0.0.0"
if [ -f "${VERSION_FILE}" ]; then
  CURRENT_VERSION="$(tr -d '[:space:]' < "${VERSION_FILE}")"
fi

cd "${PROJECT_DIR}"

if [ "${SKIP_BACKUP:-}" != "1" ]; then
  echo "▶ Backup antes do upgrade (${CURRENT_VERSION} → ${NEW_VERSION})"
  "${SCRIPT_DIR}/backup-volumes.sh" "${BACKUP_ROOT:-./backups}"
else
  echo "▶ SKIP_BACKUP=1 — backup ignorado (apenas desenvolvimento)"
fi

echo "▶ Atualizando LEX_PACS_VERSION: ${CURRENT_VERSION} → ${NEW_VERSION}"
echo "${NEW_VERSION}" > "${VERSION_FILE}"
export LEX_PACS_VERSION="${NEW_VERSION}"

echo "▶ Rebuild e reinício dos containers"
docker compose -f "${COMPOSE_FILE}" build --pull
docker compose -f "${COMPOSE_FILE}" up -d

if [ -x "${SCRIPT_DIR}/migrate.sh" ]; then
  echo "▶ Migrações de banco"
  "${SCRIPT_DIR}/migrate.sh"
else
  echo "▶ Sem migrate.sh — nenhuma migração de banco nesta versão"
fi

echo "▶ Smoke test pós-upgrade"
"${SCRIPT_DIR}/smoke-test.sh"

echo
echo "Upgrade concluído: ${CURRENT_VERSION} → ${NEW_VERSION}"
echo "Rollback: ./scripts/rollback.sh ${CURRENT_VERSION}"
