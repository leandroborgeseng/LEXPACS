#!/usr/bin/env bash
# Importa estudos do volume SQLite legado (orthanc-data) para o Orthanc com PostgreSQL.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LEGACY_VOL="ohif-viewer_orthanc-data"
LEGACY_PORT="${LEGACY_PORT:-8043}"
TARGET_URL="${ORTHANC_URL:-http://localhost:8042}"
LEGACY_CONFIG="${PROJECT_DIR}/orthanc/orthanc.legacy.json"

cd "${PROJECT_DIR}"

if ! docker volume inspect "${LEGACY_VOL}" >/dev/null 2>&1; then
  echo "Volume legado ${LEGACY_VOL} não encontrado — nada a importar."
  exit 0
fi

count=$(curl -fsS "${TARGET_URL}/tools/find" -H "Content-Type: application/json" \
  -d '{"Level":"Study","Query":{}}' | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)
if [ "${count}" != "0" ]; then
  echo "Destino já possui ${count} estudo(s) — importação ignorada."
  exit 0
fi

echo "▶ Exportando estudos do volume legado SQLite..."

docker rm -f orthanc-legacy-export >/dev/null 2>&1 || true
docker run -d --name orthanc-legacy-export \
  -v "${LEGACY_VOL}:/var/lib/orthanc/db" \
  -v "${LEGACY_CONFIG}:/etc/orthanc/orthanc.json:ro" \
  -p "${LEGACY_PORT}:8042" \
  jodogne/orthanc-plugins:1.12.5 >/dev/null

cleanup() { docker rm -f orthanc-legacy-export >/dev/null 2>&1 || true; }
trap cleanup EXIT

for _ in $(seq 1 30); do
  if curl -fsS "http://localhost:${LEGACY_PORT}/system" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

python3 <<PY
import io, json, sys, zipfile
import urllib.request

legacy = "http://localhost:${LEGACY_PORT}"
target = "${TARGET_URL}"

def get(url):
    with urllib.request.urlopen(url) as r:
        return r.read()

studies = json.loads(get(f"{legacy}/studies"))
if not studies:
    print("Nenhum estudo no volume legado.")
    sys.exit(0)

print(f"Importando {len(studies)} estudo(s)...")
imported = 0
for sid in studies:
    archive = get(f"{legacy}/studies/{sid}/archive")
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".dcm"):
                continue
            data = zf.read(name)
            req = urllib.request.Request(
                f"{target}/instances",
                data=data,
                method="POST",
                headers={"Content-Type": "application/dicom"},
            )
            try:
                urllib.request.urlopen(req)
                imported += 1
            except Exception as exc:
                print(f"  aviso: {name}: {exc}", file=sys.stderr)

print(f"Instâncias importadas: {imported}")
PY

echo "Importação concluída."
