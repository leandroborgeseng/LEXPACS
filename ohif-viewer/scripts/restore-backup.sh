#!/usr/bin/env bash
# Restaura volumes LEX PACS a partir de um snapshot de backup (E5/E6).
#
# Uso:
#   ./scripts/restore-backup.sh ./backups/2026-06-18_120000

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_DIR}/docker-compose.yml}"

SNAPSHOT="${1:-}"
if [ -z "${SNAPSHOT}" ] || [ ! -d "${SNAPSHOT}" ]; then
  echo "Uso: $0 <diretório-do-backup>" >&2
  exit 1
fi

cd "${PROJECT_DIR}"

echo "Restore LEX PACS ← ${SNAPSHOT}"
echo "Parando containers..."
docker compose -f "${COMPOSE_FILE}" down

restore_volume() {
  local vol=$1 archive=$2
  if [ ! -f "${archive}" ]; then
    echo "  ○ ${vol}: arquivo ausente — ignorando"
    return 0
  fi
  if ! docker volume inspect "${vol}" >/dev/null 2>&1; then
    docker volume create "${vol}" >/dev/null
  fi
  echo "  • ${vol}"
  docker run --rm -v "${vol}:/data" -v "${SNAPSHOT}:/backup:ro" alpine \
    sh -c "rm -rf /data/* /data/.[!.]* 2>/dev/null; tar xzf /backup/$(basename "${archive}") -C /data"
}

for prefix in ohif-viewer lex-pacs; do
  restore_volume "${prefix}_server-data" "${SNAPSHOT}/${prefix}_server-data.tar.gz" || true
  if [ ! -f "${SNAPSHOT}/${prefix}_server-data.tar.gz" ] && [ -f "${SNAPSHOT}/${prefix}_orthanc-storage.tar.gz" ]; then
    restore_volume "${prefix}_server-data" "${SNAPSHOT}/${prefix}_orthanc-storage.tar.gz"
  fi
  restore_volume "${prefix}_server-config" "${SNAPSHOT}/${prefix}_server-config.tar.gz" || true
  if [ ! -f "${SNAPSHOT}/${prefix}_server-config.tar.gz" ] && [ -f "${SNAPSHOT}/${prefix}_orthanc-config.tar.gz" ]; then
    restore_volume "${prefix}_server-config" "${SNAPSHOT}/${prefix}_orthanc-config.tar.gz"
  fi
  restore_volume "${prefix}_lex-reports" "${SNAPSHOT}/${prefix}_lex-reports.tar.gz" || true
done

if [ -f "${SNAPSHOT}/ohif-viewer_orthanc-data.tar.gz" ]; then
  restore_volume ohif-viewer_server-data "${SNAPSHOT}/ohif-viewer_orthanc-data.tar.gz" || \
    restore_volume ohif-viewer_orthanc-storage "${SNAPSHOT}/ohif-viewer_orthanc-data.tar.gz"
fi

if [ -f "${SNAPSHOT}/htpasswd" ]; then
  cp "${SNAPSHOT}/htpasswd" "${PROJECT_DIR}/nginx/.htpasswd"
  echo "  • htpasswd restaurado"
fi

if [ -f "${SNAPSHOT}/manifest.json" ]; then
  LEX_VER=$(python3 -c "import json; print(json.load(open('${SNAPSHOT}/manifest.json')).get('lex_pacs_version',''))" 2>/dev/null || true)
  if [ -n "${LEX_VER}" ] && [ -f "${PROJECT_DIR}/LEX_PACS_VERSION" ]; then
    echo "${LEX_VER}" > "${PROJECT_DIR}/LEX_PACS_VERSION"
    echo "  • LEX_PACS_VERSION restaurado: ${LEX_VER}"
  fi
fi

export LEX_PACS_VERSION="$(tr -d '[:space:]' < "${PROJECT_DIR}/LEX_PACS_VERSION" 2>/dev/null || echo 0.5.0)"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-orthanc}"

echo "Subindo database..."
docker compose -f "${COMPOSE_FILE}" up -d database
for _ in $(seq 1 30); do
  if docker compose -f "${COMPOSE_FILE}" exec -T database pg_isready -U "${POSTGRES_USER:-orthanc}" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if [ -f "${SNAPSHOT}/postgres.dump" ]; then
  echo "  • postgres.dump"
  docker compose -f "${COMPOSE_FILE}" exec -T database \
    psql -U "${POSTGRES_USER:-orthanc}" -d "${POSTGRES_DB:-orthanc}" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null 2>&1 || true
  docker compose -f "${COMPOSE_FILE}" exec -T database \
    psql -U "${POSTGRES_USER:-orthanc}" -d "${POSTGRES_DB:-orthanc}" < "${SNAPSHOT}/postgres.dump"
fi

echo "Subindo demais containers..."
docker compose -f "${COMPOSE_FILE}" up -d

echo "Restore concluído. Rode: ./scripts/smoke-test.sh"
