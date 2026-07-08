#!/bin/sh
set -e

# Roda no namespace de rede do container `database`.
# Usa socket Unix (pg_hba: local trust) para poder corrigir senha mesmo quando
# POSTGRES_PASSWORD no Coolify diverge da senha gravada no volume.

normalize_postgres_password() {
  _v="${POSTGRES_PASSWORD}"
  case "${_v}" in
    \"*) _v="${_v#\"}"; _v="${_v%\"}" ;;
  esac
  case "${_v}" in
    \'*) _v="${_v#\'}"; _v="${_v%\'}" ;;
  esac
  case "${_v}" in
    POSTGRES_PASSWORD=*) _v="${_v#POSTGRES_PASSWORD=}" ;;
  esac
  POSTGRES_PASSWORD="${_v}"
}

normalize_postgres_password
_pass_sql=$(printf '%s' "${POSTGRES_PASSWORD}" | sed "s/'/''/g")

for _attempt in $(seq 1 30); do
  if pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Sem -h: conexão local via socket (trust), não exige a senha antiga.
psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -c "ALTER USER \"${POSTGRES_USER}\" WITH PASSWORD '${_pass_sql}';"

echo "[lex-pacs] Senha PostgreSQL sincronizada com POSTGRES_PASSWORD"
