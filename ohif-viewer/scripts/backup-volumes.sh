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

for vol in ohif-viewer_orthanc-storage ohif-viewer_orthanc-config ohif-viewer_lex-reports ohif-viewer_lex-audit; do
  if docker volume inspect "$vol" >/dev/null 2>&1; then
    echo "  • ${vol}"
    docker run --rm -v "${vol}:/data:ro" -v "${DEST}:/backup" alpine \
      tar czf "/backup/${vol}.tar.gz" -C /data .
  else
    echo "  • ${vol} (não encontrado — ignorando)"
  fi
done

# Volume legado (pré-E3) — incluir se ainda existir
if docker volume inspect ohif-viewer_orthanc-data >/dev/null 2>&1; then
  echo "  • ohif-viewer_orthanc-data (legado)"
  docker run --rm -v ohif-viewer_orthanc-data:/data:ro -v "${DEST}:/backup" alpine \
    tar czf "/backup/ohif-viewer_orthanc-data.tar.gz" -C /data .
fi

COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
if [ -f "${COMPOSE_FILE}" ] && docker compose -f "${COMPOSE_FILE}" ps postgres 2>/dev/null | grep -qiE 'running|up'; then
  echo "  • postgres (pg_dump)"
  if docker compose -f "${COMPOSE_FILE}" exec -T postgres \
    pg_dump -U "${POSTGRES_USER:-orthanc}" "${POSTGRES_DB:-orthanc}" \
    > "${DEST}/postgres.dump"; then
    :
  else
    echo "  ○ pg_dump falhou — postgres pode estar indisponível"
    rm -f "${DEST}/postgres.dump"
  fi
fi

if [ -f "${PROJECT_DIR}/nginx/.htpasswd" ]; then
  cp "${PROJECT_DIR}/nginx/.htpasswd" "${DEST}/htpasswd"
fi

IMAGES_LINES=""
if command -v docker >/dev/null 2>&1 && [ -f "${COMPOSE_FILE}" ]; then
  IMAGES_LINES=$(cd "${PROJECT_DIR}" && docker compose images 2>/dev/null | tail -n +2 || true)
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
    "compose_project": "ohif-viewer",
    "lex_pacs_version": "${LEX_VERSION}",
    "volumes": ["orthanc-storage", "orthanc-config", "lex-reports", "lex-audit", "postgres-data"],
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

echo "Concluído: ${DEST}"
