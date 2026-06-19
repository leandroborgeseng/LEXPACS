#!/bin/sh
# Agendador de backup LEX PACS (container sidecar ou cron manual).
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
INTERVAL_SEC=$((INTERVAL_HOURS * 3600))
BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
RETENTION_DAILY="${BACKUP_RETENTION_DAILY:-7}"
RETENTION_WEEKLY="${BACKUP_RETENTION_WEEKLY:-4}"

echo "LEX PACS backup scheduler — intervalo ${INTERVAL_HOURS}h, retenção ${RETENTION_DAILY}d + ${RETENTION_WEEKLY}sem"

while true; do
  echo "[$(date -Iseconds)] Iniciando backup…"
  if COMPOSE_DIR="${COMPOSE_PROJECT_DIR:-}" BACKUP_ROOT="${BACKUP_ROOT}" \
    "${SCRIPT_DIR}/backup-volumes.sh" "${BACKUP_ROOT}"; then
    echo "[$(date -Iseconds)] Backup concluído"
  else
    echo "[$(date -Iseconds)] Backup falhou" >&2
  fi
  BACKUP_RETENTION_DAILY="${RETENTION_DAILY}" BACKUP_RETENTION_WEEKLY="${RETENTION_WEEKLY}" \
    "${SCRIPT_DIR}/backup-retention.sh" "${BACKUP_ROOT}" || true
  echo "[$(date -Iseconds)] Próximo backup em ${INTERVAL_HOURS}h"
  sleep "${INTERVAL_SEC}"
done
