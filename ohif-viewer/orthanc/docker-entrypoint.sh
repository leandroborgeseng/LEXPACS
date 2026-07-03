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

sync_postgres_config() {
  _tmp="${CONFIG_FILE}.tmp.$$"
  POSTGRES_HOST="${POSTGRES_HOST}" \
  POSTGRES_PORT="${POSTGRES_PORT}" \
  POSTGRES_USER="${POSTGRES_USER}" \
  POSTGRES_DB="${POSTGRES_DB}" \
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  awk '
BEGIN {
  host = ENVIRON["POSTGRES_HOST"]
  port = ENVIRON["POSTGRES_PORT"]
  user = ENVIRON["POSTGRES_USER"]
  db = ENVIRON["POSTGRES_DB"]
  pass = ENVIRON["POSTGRES_PASSWORD"]
}
function json_escape(s,    i, c, out) {
  out = ""
  for (i = 1; i <= length(s); i++) {
    c = substr(s, i, 1)
    if (c == "\\") out = out "\\\\"
    else if (c == "\"") out = out "\\\""
    else out = out c
  }
  return out
}
/"PostgreSQL"/ { pg = 1 }
pg && /^  \}/ { pg = 0 }
{
  line = $0
  if (index(line, "__LEX_POSTGRES_PASSWORD__") > 0) {
    gsub(/__LEX_POSTGRES_PASSWORD__/, json_escape(pass), line)
  }
  if (pg && line ~ /"Host"/) {
    sub(/: *"[^"]*"/, ": \"" json_escape(host) "\"", line)
  } else if (pg && line ~ /"Port"/) {
    sub(/: *[0-9]+/, ": " port, line)
  } else if (pg && line ~ /"Database"/) {
    sub(/: *"[^"]*"/, ": \"" json_escape(db) "\"", line)
  } else if (pg && line ~ /"Username"/) {
    sub(/: *"[^"]*"/, ": \"" json_escape(user) "\"", line)
  } else if (pg && line ~ /"Password"/) {
    sub(/: *"[^"]*"/, ": \"" json_escape(pass) "\"", line)
  }
  print line
}
' "${CONFIG_FILE}" > "${_tmp}"

  if ! cmp -s "${_tmp}" "${CONFIG_FILE}" 2>/dev/null; then
    mv "${_tmp}" "${CONFIG_FILE}"
  else
    rm -f "${_tmp}"
  fi
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

  return $((1 - _changed))
}

repair_config() {
  sync_postgres_config
  sanitize_config || true
}

config_hash() {
  sha256sum "${CONFIG_FILE}" 2>/dev/null | awk '{print $1}'
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
  LAST_HASH=$(config_hash)
  while true; do
    sleep 2
    NEW_HASH=$(config_hash)
    if [ -n "${NEW_HASH}" ] && [ "${NEW_HASH}" != "${LAST_HASH}" ]; then
      echo "[lex-pacs] Configuração alterada — reiniciando servidor DICOM..."
      if [ -f "${PID_FILE}" ]; then
        kill "$(cat "${PID_FILE}")" 2>/dev/null || true
      fi
      LAST_HASH="${NEW_HASH}"
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
  wait_for_postgres "${POSTGRES_HOST}" "${POSTGRES_PORT}" || true

  AET=$(grep -o '"DicomAet"[[:space:]]*:[[:space:]]*"[^"]*"' "${CONFIG_FILE}" | sed 's/.*"\([^"]*\)"$/\1/' || echo "?")
  echo "[lex-pacs] Iniciando servidor DICOM (AE Title: ${AET}, DB: ${POSTGRES_USER}@${POSTGRES_HOST}/${POSTGRES_DB})"
  Orthanc "${CONFIG_FILE}" &
  echo $! > "${PID_FILE}"
  wait "$(cat "${PID_FILE}")" || true
  sleep 2
done
