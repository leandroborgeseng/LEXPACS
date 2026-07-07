#!/bin/sh

CONFIG_DIR="/orthanc-config"
CONFIG_FILE="${CONFIG_DIR}/orthanc.json"
BASE_FILE="/etc/orthanc/orthanc.base.json"
PID_FILE="${CONFIG_DIR}/orthanc.pid"
POSTGRES_HOST="${POSTGRES_HOST:-database}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-orthanc}"
POSTGRES_DB="${POSTGRES_DB:-orthanc}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-orthanc}"

normalize_postgres_password() {
  _v="${POSTGRES_PASSWORD}"
  # Aspas externas (erro comum no Coolify/.env)
  case "${_v}" in
    \"*) _v="${_v#\"}"; _v="${_v%\"}" ;;
  esac
  case "${_v}" in
    \'*) _v="${_v#\'}"; _v="${_v%\'}" ;;
  esac
  # Valor colado como "POSTGRES_PASSWORD=senha" no campo Valor
  case "${_v}" in
    POSTGRES_PASSWORD=*) _v="${_v#POSTGRES_PASSWORD=}" ;;
  esac
  POSTGRES_PASSWORD="${_v}"
}

normalize_postgres_password

mkdir -p "${CONFIG_DIR}" /var/lib/orthanc/worklists

if [ ! -f "${CONFIG_FILE}" ]; then
  cp "${BASE_FILE}" "${CONFIG_FILE}"
fi

json_field() {
  _key="$1"
  grep "\"${_key}\"" "${CONFIG_FILE}" 2>/dev/null | head -1 | sed -n 's/.*"'"${_key}"'"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
}

tls_file_ok() {
  _path="$1"
  [ -n "${_path}" ] && [ -f "${_path}" ] && [ -r "${_path}" ]
}

cert_pem_ok() {
  _path="$1"
  tls_file_ok "${_path}" && openssl x509 -in "${_path}" -noout 2>/dev/null
}

key_pem_ok() {
  _path="$1"
  tls_file_ok "${_path}" && (openssl rsa -in "${_path}" -noout 2>/dev/null || openssl ec -in "${_path}" -noout 2>/dev/null)
}

validate_config_json() {
  jq empty "${CONFIG_FILE}" 2>/dev/null
}

reset_config_from_base() {
  echo "[lex-pacs] Restaurando orthanc.json a partir do template base" >&2
  cp "${BASE_FILE}" "${CONFIG_FILE}"
}

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
' "${CONFIG_FILE}" > "${_tmp}" || return 1

  if ! cmp -s "${_tmp}" "${CONFIG_FILE}" 2>/dev/null; then
    mv "${_tmp}" "${CONFIG_FILE}"
  else
    rm -f "${_tmp}"
  fi
}

sanitize_config() {
  if grep -q '"IngestTranscoding"[[:space:]]*:[[:space:]]*""' "${CONFIG_FILE}" 2>/dev/null; then
    sed -i '/"IngestTranscoding"[[:space:]]*:[[:space:]]*""/d' "${CONFIG_FILE}"
  fi

  if grep -q '"HttpServerEnabled"[[:space:]]*:[[:space:]]*false' "${CONFIG_FILE}" 2>/dev/null; then
    echo "[lex-pacs] HttpServerEnabled forçado para true (healthcheck HTTP)" >&2
    sed -i 's/"HttpServerEnabled"[[:space:]]*:[[:space:]]*false/"HttpServerEnabled": true/' "${CONFIG_FILE}"
  fi

  _tls_cert=$(json_field DicomTlsCertificate)
  _tls_key=$(json_field DicomTlsPrivateKey)
  _tls_trusted=$(json_field DicomTlsTrustedCertificates)
  if grep -q '"DicomTlsEnabled"[[:space:]]*:[[:space:]]*true' "${CONFIG_FILE}" 2>/dev/null; then
    _tls_bad=0
    if ! cert_pem_ok "${_tls_cert}" || ! key_pem_ok "${_tls_key}"; then
      _tls_bad=1
    elif [ -n "${_tls_trusted}" ] && ! cert_pem_ok "${_tls_trusted}"; then
      _tls_bad=1
    fi
    if [ "${_tls_bad}" -eq 1 ]; then
      echo "[lex-pacs] DICOM TLS desabilitado — certificados ausentes, ilegíveis ou inválidos" >&2
      sed -i 's/"DicomTlsEnabled"[[:space:]]*:[[:space:]]*true/"DicomTlsEnabled": false/' "${CONFIG_FILE}"
    fi
  fi

  _ssl_cert=$(json_field SslCertificate)
  if grep -q '"SslEnabled"[[:space:]]*:[[:space:]]*true' "${CONFIG_FILE}" 2>/dev/null; then
    if ! cert_pem_ok "${_ssl_cert}"; then
      echo "[lex-pacs] SslEnabled desabilitado — certificado HTTPS ausente" >&2
      sed -i 's/"SslEnabled"[[:space:]]*:[[:space:]]*true/"SslEnabled": false/' "${CONFIG_FILE}"
    fi
  fi
}

strip_postgres_connection_uri() {
  if jq -e '.PostgreSQL.ConnectionUri // empty | length > 0' "${CONFIG_FILE}" >/dev/null 2>&1; then
    echo "[lex-pacs] Removendo PostgreSQL.ConnectionUri inválido (usa Host/Port/Password)" >&2
    jq 'del(.PostgreSQL.ConnectionUri)' "${CONFIG_FILE}" > "${CONFIG_FILE}.uri.$$" \
      && mv "${CONFIG_FILE}.uri.$$" "${CONFIG_FILE}"
  fi
}

repair_config() {
  if ! validate_config_json; then
    reset_config_from_base
  fi
  strip_postgres_connection_uri || true
  sync_postgres_config || true
  sanitize_config || true
  if ! validate_config_json; then
    reset_config_from_base
    sync_postgres_config || true
    sanitize_config || true
  fi
}

config_hash() {
  sha256sum "${CONFIG_FILE}" 2>/dev/null | awk '{print $1}' || echo 0
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

start_orthanc() {
  AET=$(json_field DicomAet)
  AET=${AET:-?}
  echo "[lex-pacs] Iniciando servidor DICOM (AE Title: ${AET}, DB: ${POSTGRES_USER}@${POSTGRES_HOST}/${POSTGRES_DB})"
  rm -f "${PID_FILE}"
  Orthanc "${CONFIG_FILE}" 2>&1 &
  _pid=$!
  echo "${_pid}" > "${PID_FILE}"

  _wait=0
  while [ "${_wait}" -lt 90 ]; do
    if wget -qO- http://127.0.0.1:8042/system >/dev/null 2>&1; then
      echo "[lex-pacs] API HTTP disponível em :8042"
      return 0
    fi
    if ! kill -0 "${_pid}" 2>/dev/null; then
      echo "[lex-pacs] ERRO: Orthanc encerrou durante a subida (pid ${_pid})" >&2
      rm -f "${PID_FILE}"
      return 1
    fi
    sleep 2
    _wait=$((_wait + 2))
  done

  echo "[lex-pacs] AVISO: API HTTP ainda não respondeu após 90s" >&2
  return 0
}

watch_config() {
  LAST_HASH=$(config_hash)
  while true; do
    sleep 2
    NEW_HASH=$(config_hash)
    if [ -n "${NEW_HASH}" ] && [ "${NEW_HASH}" != "${LAST_HASH}" ]; then
      echo "[lex-pacs] Configuração alterada — reiniciando servidor DICOM..."
      if [ -f "${PID_FILE}" ]; then
        kill "$(cat "${PID_FILE}")" 2>/dev/null || true
        rm -f "${PID_FILE}"
      fi
      LAST_HASH="${NEW_HASH}"
    fi
  done
}

WATCH_PID=""
cleanup() {
  if [ -n "${WATCH_PID}" ]; then
    kill "${WATCH_PID}" 2>/dev/null || true
  fi
  if [ -f "${PID_FILE}" ]; then
    kill "$(cat "${PID_FILE}")" 2>/dev/null || true
    rm -f "${PID_FILE}"
  fi
}
trap cleanup EXIT INT TERM

_bootstrapped=0
while true; do
  repair_config
  wait_for_postgres "${POSTGRES_HOST}" "${POSTGRES_PORT}" || true

  if start_orthanc; then
    if [ "${_bootstrapped}" -eq 0 ]; then
      _bootstrapped=1
      watch_config &
      WATCH_PID=$!
    fi
    wait "$(cat "${PID_FILE}")" 2>/dev/null || true
  else
    reset_config_from_base
    repair_config
  fi

  sleep 2
done
