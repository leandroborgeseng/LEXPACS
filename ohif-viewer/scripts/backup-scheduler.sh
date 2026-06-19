#!/bin/sh
# Agendador de backup LEX PACS (container sidecar ou cron manual).
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
INTERVAL_SEC=$((INTERVAL_HOURS * 3600))
BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

echo "LEX PACS backup scheduler — intervalo ${INTERVAL_HOURS}h, retenção ${RETENTION_DAYS} dias"

while true; do
  echo "[$(date -Iseconds)] Iniciando backup…"
  if COMPOSE_DIR="${COMPOSE_PROJECT_DIR:-}" BACKUP_ROOT="${BACKUP_ROOT}" \
    "${SCRIPT_DIR}/backup-volumes.sh" "${BACKUP_ROOT}"; then
    echo "[$(date -Iseconds)] Backup concluído"
  else
    echo "[$(date -Iseconds)] Backup falhou" >&2
  fi
  "${SCRIPT_DIR}/backup-retention.sh" "${BACKUP_ROOT}" "${RETENTION_DAYS}" || true
  echo "[$(date -Iseconds)] Próximo backup em ${INTERVAL_HOURS}h"
  sleep "${INTERVAL_SEC}"
done
