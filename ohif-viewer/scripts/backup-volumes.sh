#!/bin/sh
# Backup manual dos volumes LEX PACS (executar na pasta ohif-viewer).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="${COMPOSE_DIR:-$(dirname "$SCRIPT_DIR")}"
BACKUP_ROOT="${1:-./backups}"
STAMP=$(date +%Y-%m-%d_%H%M%S)
DEST="${BACKUP_ROOT}/${STAMP}"
mkdir -p "${DEST}"

LEX_VERSION="unknown"
if [ -f "${PROJECT_DIR}/LEX_PACS_VERSION" ]; then
  LEX_VERSION="$(tr -d '[:space:]' < "${PROJECT_DIR}/LEX_PACS_VERSION")"
fi

echo "Backup LEX PACS → ${DEST}"

vol_exists() {
  docker volume inspect "$1" >/dev/null 2>&1
}

backup_vol() {
  local vol=$1
  if vol_exists "$vol"; then
    echo "  • ${vol}"
    docker run --rm -v "${vol}:/data:ro" -v "${DEST}:/backup" alpine \
      tar czf "/backup/${vol}.tar.gz" -C /data .
    return 0
  fi
  return 1
}

for prefix in lex-pacs ohif-viewer; do
  for suffix in server-data server-config lex-reports lex-audit; do
    backup_vol "${prefix}_${suffix}" || true
  done
done

# Volumes legados (pré-renome)
for vol in ohif-viewer_orthanc-storage ohif-viewer_orthanc-config lex-pacs_orthanc-storage lex-pacs_orthanc-config; do
  backup_vol "$vol" || true
done

if vol_exists ohif-viewer_orthanc-data; then
  echo "  • ohif-viewer_orthanc-data (legado)"
  docker run --rm -v ohif-viewer_orthanc-data:/data:ro -v "${DEST}:/backup" alpine \
    tar czf "/backup/ohif-viewer_orthanc-data.tar.gz" -C /data .
fi

COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_DIR}/docker-compose.yml}"
if [ -f "${COMPOSE_FILE}" ] && docker compose -f "${COMPOSE_FILE}" ps database 2>/dev/null | grep -qiE 'running|up'; then
  echo "  • database (pg_dump)"
  if docker compose -f "${COMPOSE_FILE}" exec -T database \
    pg_dump -U "${POSTGRES_USER:-orthanc}" "${POSTGRES_DB:-orthanc}" \
    > "${DEST}/postgres.dump"; then
    :
  else
    echo "  ○ pg_dump falhou — database pode estar indisponível"
    rm -f "${DEST}/postgres.dump"
  fi
fi

if [ -f "${PROJECT_DIR}/nginx/.htpasswd" ]; then
  cp "${PROJECT_DIR}/nginx/.htpasswd" "${DEST}/htpasswd"
fi

IMAGES_LINES=""
if command -v docker >/dev/null 2>&1 && [ -f "${COMPOSE_FILE}" ]; then
  IMAGES_LINES=$(cd "${PROJECT_DIR}" && docker compose -f "${COMPOSE_FILE}" images 2>/dev/null | tail -n +2 || true)
fi

COMPOSE_PROJECT="$(basename "$(dirname "${COMPOSE_FILE}")")"
if [ -f "${PROJECT_DIR}/../docker-compose.coolify.yml" ] && [ "${COMPOSE_FILE}" = "${PROJECT_DIR}/../docker-compose.coolify.yml" ]; then
  COMPOSE_PROJECT="lex-pacs"
fi

python3 <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

images = []
for line in """${IMAGES_LINES}""".strip().splitlines():
    parts = line.split()
    if len(parts) >= 2:
        images.append({"service": parts[0], "image": parts[1]})

manifest = {
    "created_at": "${STAMP}",
    "compose_project": "${COMPOSE_PROJECT}",
    "lex_pacs_version": "${LEX_VERSION}",
    "volumes": ["server-data", "server-config", "lex-reports", "lex-audit", "database-data"],
    "images": images,
}
Path("${DEST}/manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

status = {
    "success": True,
    "last_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "last_path": "${STAMP}",
    "backup_root": "${BACKUP_ROOT}",
    "lex_pacs_version": "${LEX_VERSION}",
    "destination": "${DEST}",
}
root = Path("${BACKUP_ROOT}")
root.mkdir(parents=True, exist_ok=True)
(root / "latest-status.json").write_text(json.dumps(status, indent=2) + "\n")
PY

if vol_exists lex-pacs_lex-backups; then
  echo "  • lex-pacs_lex-backups (latest-status.json)"
  docker run --rm \
    -v lex-pacs_lex-backups:/lex-backups \
    -v "${BACKUP_ROOT}:/src:ro" \
    alpine cp /src/latest-status.json /lex-backups/latest-status.json
fi

echo "Concluído: ${DEST}"
