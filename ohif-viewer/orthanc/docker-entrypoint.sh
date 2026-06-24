#!/bin/sh
set -e

CONFIG_DIR="/orthanc-config"
CONFIG_FILE="${CONFIG_DIR}/orthanc.json"
BASE_FILE="/etc/orthanc/orthanc.base.json"
PID_FILE="${CONFIG_DIR}/orthanc.pid"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-orthanc}"

mkdir -p "${CONFIG_DIR}" /var/lib/orthanc/worklists

if [ ! -f "${CONFIG_FILE}" ]; then
  cp "${BASE_FILE}" "${CONFIG_FILE}"
fi

# Alinha host PostgreSQL ao template (ex.: rename database no compose)
BASE_HOST=$(grep -A20 '"PostgreSQL"' "${BASE_FILE}" | grep '"Host"' | head -1 | sed 's/.*: "\([^"]*\)".*/\1/')
if [ -n "${BASE_HOST}" ]; then
  sed -i "/\"PostgreSQL\"/,/}/ s/\"Host\": \"[^\"]*\"/\"Host\": \"${BASE_HOST}\"/" "${CONFIG_FILE}"
fi

# Injeta senha PostgreSQL sem expor no repositório
sed -i "s|__LEX_POSTGRES_PASSWORD__|${POSTGRES_PASSWORD}|g" "${CONFIG_FILE}"

sanitize_config() {
  if grep -q '"IngestTranscoding"[[:space:]]*:[[:space:]]*""' "${CONFIG_FILE}" 2>/dev/null; then
    sed -i '/"IngestTranscoding"[[:space:]]*:[[:space:]]*""/d' "${CONFIG_FILE}"
  fi
}

sanitize_config

watch_config() {
  LAST_MTIME=$(stat -c %Y "${CONFIG_FILE}" 2>/dev/null || echo 0)
  while true; do
    sleep 2
    NEW_MTIME=$(stat -c %Y "${CONFIG_FILE}" 2>/dev/null || echo 0)
    if [ "${NEW_MTIME}" != "${LAST_MTIME}" ]; then
      echo "[lex-pacs] Configuração alterada — reiniciando servidor DICOM..."
      sed -i "s|__LEX_POSTGRES_PASSWORD__|${POSTGRES_PASSWORD}|g" "${CONFIG_FILE}"
      sanitize_config
      if [ -f "${PID_FILE}" ]; then
        kill "$(cat "${PID_FILE}")" 2>/dev/null || true
      fi
      LAST_MTIME=$(stat -c %Y "${CONFIG_FILE}" 2>/dev/null || echo 0)
    fi
  done
}

watch_config &
WATCH_PID=$!

cleanup() {
  kill "${WATCH_PID}" 2>/dev/null || true
  if [ -f "${PID_FILE}" ]; then
    kill "$(cat "${PID_FILE}")" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

while true; do
  AET=$(grep -o '"DicomAet"[[:space:]]*:[[:space:]]*"[^"]*"' "${CONFIG_FILE}" | sed 's/.*"\([^"]*\)"$/\1/' || echo "?")
  echo "[lex-pacs] Iniciando servidor DICOM (AE Title: ${AET})"
  Orthanc "${CONFIG_FILE}" &
  echo $! > "${PID_FILE}"
  wait "$(cat "${PID_FILE}")" || true
  sleep 1
done
