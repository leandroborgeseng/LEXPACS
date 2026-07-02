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

config_field_needs_update() {
  _field="$1"
  _expected="$2"
  _current=$(postgres_field "${_field}")
  [ "${_current}" != "${_expected}" ]
}

sync_postgres_config() {
  _needs_sync=0
  _pass_esc=$(escape_sed "${POSTGRES_PASSWORD}")
  _user_esc=$(escape_sed "${POSTGRES_USER}")
  _db_esc=$(escape_sed "${POSTGRES_DB}")
  _host_esc=$(escape_sed "${POSTGRES_HOST}")

  if grep -q '__LEX_POSTGRES_PASSWORD__' "${CONFIG_FILE}" 2>/dev/null; then
    _needs_sync=1
  fi
  if config_field_needs_update Host "${POSTGRES_HOST}"; then _needs_sync=1; fi
  if config_field_needs_update Port "${POSTGRES_PORT}"; then _needs_sync=1; fi
  if config_field_needs_update Database "${POSTGRES_DB}"; then _needs_sync=1; fi
  if config_field_needs_update Username "${POSTGRES_USER}"; then _needs_sync=1; fi
  if config_field_needs_update Password "${POSTGRES_PASSWORD}"; then _needs_sync=1; fi

  if [ "${_needs_sync}" -eq 0 ]; then
    return 0
  fi

  _tmp="${CONFIG_FILE}.tmp.$$"
  cp "${CONFIG_FILE}" "${_tmp}"

  sed -i "s/__LEX_POSTGRES_PASSWORD__/${_pass_esc}/g" "${_tmp}"
  sed -i "/\"PostgreSQL\"/,/^  }/ s/\"Host\": \"[^\"]*\"/\"Host\": \"${_host_esc}\"/" "${_tmp}"
  sed -i "/\"PostgreSQL\"/,/^  }/ s/\"Port\": [0-9]*/\"Port\": ${POSTGRES_PORT}/" "${_tmp}"
  sed -i "/\"PostgreSQL\"/,/^  }/ s/\"Database\": \"[^\"]*\"/\"Database\": \"${_db_esc}\"/" "${_tmp}"
  sed -i "/\"PostgreSQL\"/,/^  }/ s/\"Username\": \"[^\"]*\"/\"Username\": \"${_user_esc}\"/" "${_tmp}"
  sed -i "/\"PostgreSQL\"/,/^  }/ s/\"Password\": \"[^\"]*\"/\"Password\": \"${_pass_esc}\"/" "${_tmp}"

  mv "${_tmp}" "${CONFIG_FILE}"
}

sanitize_config() {
  _changed=0

  if grep -q '"IngestTranscoding"[[:space:]]*:[[:space:]]*""' "${CONFIG_FILE}" 2>/dev/null; then
    sed -i '/"IngestTranscoding"[[:space:]]*:[[:space:]]*""/d' "${CONFIG_FILE}"
    _changed=1
  fi

  if grep -q '"DicomTlsEnabled"[[:space:]]*:[[:space:]]*true' "${CONFIG_FILE}" 2>/dev/null; then
    _tls_cert=$(grep '"DicomTlsCertificate"' "${CONFIG_FILE}" 2>/dev/null | sed -n 's/.*"DicomTlsCertificate"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    _tls_key=$(grep '"DicomTlsPrivateKey"' "${CONFIG_FILE}" 2>/dev/null | sed -n 's/.*"DicomTlsPrivateKey"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    if [ -z "${_tls_cert}" ] || [ ! -f "${_tls_cert}" ] || [ -z "${_tls_key}" ] || [ ! -f "${_tls_key}" ]; then
      echo "[lex-pacs] DICOM TLS desabilitado — certificados ausentes em ${CONFIG_DIR}/dicom-tls" >&2
      sed -i 's/"DicomTlsEnabled"[[:space:]]*:[[:space:]]*true/"DicomTlsEnabled": false/' "${CONFIG_FILE}"
      _changed=1
    fi
  fi

  [ "${_changed}" -eq 1 ]
}

repair_config() {
  sync_postgres_config
  sanitize_config || true
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
