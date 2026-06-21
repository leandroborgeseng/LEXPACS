#!/usr/bin/env bash
# Migração E3: SQLite + orthanc-data → PostgreSQL + orthanc-storage
#
# Uso (na pasta ohif-viewer, com stack parado ou orthanc parado):
#   ./scripts/migrate-e3.sh
#
# Idempotente: pode rodar várias vezes com segurança.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
BASE_CONFIG="${PROJECT_DIR}/orthanc/orthanc.base.json"

OLD_VOL="ohif-viewer_orthanc-data"
STORAGE_VOL="ohif-viewer_server-data"
CONFIG_VOL="ohif-viewer_server-config"
FLAG_NAME=".e3-migrated"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-orthanc}"

cd "${PROJECT_DIR}"

volume_empty() {
  local vol=$1
  docker run --rm -v "${vol}:/data:ro" alpine \
    sh -c '[ -z "$(ls -A /data 2>/dev/null)" ]'
}

flag_exists() {
  docker run --rm -v "${CONFIG_VOL}:/cfg:ro" alpine \
    test -f "/cfg/${FLAG_NAME}"
}

echo "▶ Migração E3 — PostgreSQL + orthanc-storage"

if flag_exists 2>/dev/null; then
  echo "  ○ Já migrado (${FLAG_NAME} presente) — nada a fazer"
  exit 0
fi

echo "  • Parando server..."
docker compose -f "${COMPOSE_FILE}" stop server 2>/dev/null || true

MIGRATED_STORAGE=0
if docker volume inspect "${OLD_VOL}" >/dev/null 2>&1; then
  if volume_empty "${STORAGE_VOL}"; then
    echo "  • Copiando ${OLD_VOL} → ${STORAGE_VOL}"
    docker run --rm -v "${OLD_VOL}:/from:ro" -v "${STORAGE_VOL}:/to" alpine \
      sh -c 'cp -a /from/. /to/'
    echo "  • Removendo índice SQLite legado"
    docker run --rm -v "${STORAGE_VOL}:/data" alpine \
      sh -c 'rm -f /data/index /data/index-wal /data/index-shm'
    MIGRATED_STORAGE=1
  else
    echo "  ○ ${STORAGE_VOL} já contém dados — cópia ignorada"
  fi
else
  echo "  ○ Volume legado ${OLD_VOL} não encontrado (instalação nova)"
fi

echo "  • Atualizando orthanc.json no volume de configuração"
python3 <<PY
import json
from pathlib import Path

base = json.loads(Path("${BASE_CONFIG}").read_text())
base["PostgreSQL"]["Password"] = "${POSTGRES_PASSWORD}"

runtime = {}
import subprocess
proc = subprocess.run(
    ["docker", "run", "--rm", "-v", "${CONFIG_VOL}:/cfg:ro", "alpine", "cat", "/cfg/orthanc.json"],
    capture_output=True, text=True,
)
if proc.returncode == 0 and proc.stdout.strip():
    try:
        runtime = json.loads(proc.stdout)
    except json.JSONDecodeError:
        runtime = {}

for key in ("DicomAet", "Name"):
    if key in runtime:
        base[key] = runtime[key]

merged = json.dumps(base, indent=2) + "\n"
subprocess.run(
    ["docker", "run", "--rm", "-i", "-v", "${CONFIG_VOL}:/cfg", "alpine", "sh", "-c", "cat > /cfg/orthanc.json"],
    input=merged, text=True, check=True,
)
subprocess.run(
    ["docker", "run", "--rm", "-v", "${CONFIG_VOL}:/cfg", "alpine", "sh", "-c", "date -Iseconds > /cfg/.e3-migrated"],
    check=True,
)
print("  • Configuração mesclada com template E3/E4")
PY

echo "  • Subindo database e server..."
export POSTGRES_PASSWORD
docker compose -f "${COMPOSE_FILE}" up -d database server

echo "  • Aguardando servidor DICOM..."
for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:8042/system" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if [ "${MIGRATED_STORAGE}" = "1" ]; then
  echo "  • Importando estudos do volume legado (SQLite → PostgreSQL)..."
  "${SCRIPT_DIR}/import-from-legacy.sh" || true
fi

echo "  • Subindo demais serviços..."
docker compose -f "${COMPOSE_FILE}" up -d

echo "Migração E3 concluída."
