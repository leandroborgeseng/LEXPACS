#!/usr/bin/env sh
# Wrapper: política 7 diários + 4 semanais (E5).
set -eu

BACKUP_ROOT="${1:-./backups}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

export BACKUP_RETENTION_DAILY="${BACKUP_RETENTION_DAILY:-7}"
export BACKUP_RETENTION_WEEKLY="${BACKUP_RETENTION_WEEKLY:-4}"

exec python3 "${SCRIPT_DIR}/backup-retention.py" "${BACKUP_ROOT}"
