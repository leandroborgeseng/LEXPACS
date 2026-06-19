#!/bin/sh
# Remove backups antigos além do período de retenção.
set -eu

BACKUP_ROOT="${1:-./backups}"
RETENTION_DAYS="${2:-14}"

if [ ! -d "${BACKUP_ROOT}" ]; then
  exit 0
fi

find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d ! -name '.git' -mtime +"${RETENTION_DAYS}" -print | while read -r dir; do
  echo "Retenção: removendo ${dir}"
  rm -rf "${dir}"
done
