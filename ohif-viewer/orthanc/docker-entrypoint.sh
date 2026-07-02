#!/bin/sh
set -e

CONFIG_DIR="/orthanc-config"
CONFIG_FILE="${CONFIG_DIR}/orthanc.json"
BASE_FILE="/etc/orthanc/orthanc.base.json"
PID_FILE="${CONFIG_DIR}/orthanc.pid"
POSTGRES_HOST="${POSTGRES_HOST:-database}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-orthanc}"
POSTGRES_DB="${POSTGRES_DB:-orthanc}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-orthanc}"

mkdir -p "${CONFIG_DIR}" /var/lib/orthanc/worklists

if [ ! -f "${CONFIG_FILE}" ]; then
  cp "${BASE_FILE}" "${CONFIG_FILE}"
fi

escape_sed() {
  printf '%s' "$1" | sed -e 's/[\\/&]/\\&/g'
}

postgres_field() {
  _field="$1"
  grep -A20 '"PostgreSQL"' "${CONFIG_FILE}" 2>/dev/null | grep "\"${_field}\"" | head -1 | sed 's/.*: "\?\([^",}]*\)"\?.*/\1/' || true
}

sync_postgres_config() {
  _pass_esc=$(escape_sed "${POSTGRES_PASSWORD}")
  _user_esc=$(escape_sed "${POSTGRES_USER}")
  _db_esc=$(escape_sed "${POSTGRES_DB}")
  _host_esc=$(escape_sed "${POSTGRES_HOST}")

  sed -i "s/__LEX_POSTGRES_PASSWORD__/${_pass_esc}/g" "${CONFIG_FILE}"
  sed -i "/\"PostgreSQL\"/,/^  }/ s/\"Host\": \"[^\"]*\"/\"Host\": \"${_host_esc}\"/" "${CONFIG_FILE}"
  sed -i "/\"PostgreSQL\"/,/^  }/ s/\"Port\": [0-9]*/\"Port\": ${POSTGRES_PORT}/" "${CONFIG_FILE}"
  sed -i "/\"PostgreSQL\"/,/^  }/ s/\"Database\": \"[^\"]*\"/\"Database\": \"${_db_esc}\"/" "${CONFIG_FILE}"
  sed -i "/\"PostgreSQL\"/,/^  }/ s/\"Username\": \"[^\"]*\"/\"Username\": \"${_user_esc}\"/" "${CONFIG_FILE}"
  sed -i "/\"PostgreSQL\"/,/^  }/ s/\"Password\": \"[^\"]*\"/\"Password\": \"${_pass_esc}\"/" "${CONFIG_FILE}"
}

sanitize_config() {
  if grep -q '"IngestTranscoding"[[:space:]]*:[[:space:]]*""' "${CONFIG_FILE}" 2>/dev/null; then
    sed -i '/"IngestTranscoding"[[:space:]]*:[[:space:]]*""/d' "${CONFIG_FILE}"
  fi

  if grep -q '"DicomTlsEnabled"[[:space:]]*:[[:space:]]*true' "${CONFIG_FILE}" 2>/dev/null; then
    _tls_cert=$(grep '"DicomTlsCertificate"' "${CONFIG_FILE}" 2>/dev/null | sed -n 's/.*"DicomTlsCertificate"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    _tls_key=$(grep '"DicomTlsPrivateKey"' "${CONFIG_FILE}" 2>/dev/null | sed -n 's/.*"DicomTlsPrivateKey"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    if [ -z "${_tls_cert}" ] || [ ! -f "${_tls_cert}" ] || [ -z "${_tls_key}" ] || [ ! -f "${_tls_key}" ]; then
      echo "[lex-pacs] DICOM TLS desabilitado — certificados ausentes em ${CONFIG_DIR}/dicom-tls" >&2
      sed -i 's/"DicomTlsEnabled"[[:space:]]*:[[:space:]]*true/"DicomTlsEnabled": false/' "${CONFIG_FILE}"
    fi
  fi
}

repair_config() {
  sync_postgres_config
  sanitize_config
}

wait_for_postgres() {
  _host="${1:-${POSTGRES_HOST}}"
  _port="${2:-${POSTGRES_PORT}}"
  _attempt=1
  echo "[lex-pacs] Aguardando PostgreSQL (${_host}:${_port})..."
  while [ "${_attempt}" -le 60 ]; do
    if bash -c "exec 3<>/dev/tcp/${_host}/${_port}" 2>/dev/null; then
      echo "[lex-pacs] PostgreSQL acessível"
      return 0
    fi
    sleep 2
    _attempt=$((_attempt + 1))
  done
  echo "[lex-pacs] AVISO: timeout aguardando PostgreSQL (${_host}:${_port})" >&2
  return 1
}

repair_config

watch_config() {
  LAST_MTIME=$(stat -c %Y "${CONFIG_FILE}" 2>/dev/null || echo 0)
  while true; do
    sleep 2
    NEW_MTIME=$(stat -c %Y "${CONFIG_FILE}" 2>/dev/null || echo 0)
    if [ "${NEW_MTIME}" != "${LAST_MTIME}" ]; then
      echo "[lex-pacs] Configuração alterada — reiniciando servidor DICOM..."
      repair_config
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
  repair_config
  PG_HOST=$(postgres_field Host)
  PG_PORT=$(postgres_field Port)
  PG_HOST=${PG_HOST:-${POSTGRES_HOST}}
  PG_PORT=${PG_PORT:-${POSTGRES_PORT}}
  wait_for_postgres "${PG_HOST}" "${PG_PORT}" || true

  AET=$(grep -o '"DicomAet"[[:space:]]*:[[:space:]]*"[^"]*"' "${CONFIG_FILE}" | sed 's/.*"\([^"]*\)"$/\1/' || echo "?")
  echo "[lex-pacs] Iniciando servidor DICOM (AE Title: ${AET}, DB: ${POSTGRES_USER}@${PG_HOST}/${POSTGRES_DB})"
  Orthanc "${CONFIG_FILE}" &
  echo $! > "${PID_FILE}"
  wait "$(cat "${PID_FILE}")" || true
  sleep 2
done
