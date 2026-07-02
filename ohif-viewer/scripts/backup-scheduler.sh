#!/bin/sh
# Agendador de backup LEX PACS (container sidecar ou cron manual).
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_ROOT="${BACKUP_ROOT:-/backups}"

load_portal_ops() {
  ENV_FILE="${PORTAL_OPS_ENV:-/orthanc-config/portal-ops.env}"
  if [ -f "${ENV_FILE}" ]; then
    set -a
    # shellcheck disable=SC1090
    . "${ENV_FILE}"
    set +a
  fi
  INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
  RETENTION_DAILY="${BACKUP_RETENTION_DAILY:-7}"
  RETENTION_WEEKLY="${BACKUP_RETENTION_WEEKLY:-4}"
  INTERVAL_SEC=$((INTERVAL_HOURS * 3600))
}

load_portal_ops
echo "LEX PACS backup scheduler — intervalo ${INTERVAL_HOURS}h, retenção ${RETENTION_DAILY}d + ${RETENTION_WEEKLY}sem"

while true; do
  load_portal_ops
  TRIGGER_FILE="$(dirname "${PORTAL_OPS_ENV:-/orthanc-config/portal-ops.env}")/backup-trigger"
  if [ -f "${TRIGGER_FILE}" ]; then
    rm -f "${TRIGGER_FILE}" 2>/dev/null || true
    echo "[$(date -Iseconds)] Backup manual solicitado via portal"
  fi
  echo "[$(date -Iseconds)] Iniciando backup…"
  if COMPOSE_DIR="${COMPOSE_PROJECT_DIR:-}" BACKUP_ROOT="${BACKUP_ROOT}" \
    "${SCRIPT_DIR}/backup-volumes.sh" "${BACKUP_ROOT}"; then
    echo "[$(date -Iseconds)] Backup concluído"
  else
    echo "[$(date -Iseconds)] Backup falhou" >&2
  fi
  BACKUP_RETENTION_DAILY="${RETENTION_DAILY}" BACKUP_RETENTION_WEEKLY="${RETENTION_WEEKLY}" \
    "${SCRIPT_DIR}/backup-retention.sh" "${BACKUP_ROOT}" || true
  if [ -n "${BACKUP_REMOTE_DIR:-}" ] || [ -n "${BACKUP_S3_BUCKET:-}" ]; then
    echo "[$(date -Iseconds)] Espelhando backup remoto…"
    BACKUP_ROOT="${BACKUP_ROOT}" \
      BACKUP_REMOTE_DIR="${BACKUP_REMOTE_DIR:-}" \
      BACKUP_S3_BUCKET="${BACKUP_S3_BUCKET:-}" \
      BACKUP_S3_PREFIX="${BACKUP_S3_PREFIX:-lex-pacs}" \
      AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-}" \
      AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-}" \
      AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-}" \
      AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-auto}" \
      "${SCRIPT_DIR}/backup-remote-mirror.sh" "${BACKUP_ROOT}" || \
      echo "[$(date -Iseconds)] Mirror remoto falhou (backup local preservado)" >&2
  fi
  echo "[$(date -Iseconds)] Próximo backup em ${INTERVAL_HOURS}h"
  sleep "${INTERVAL_SEC}"
done
