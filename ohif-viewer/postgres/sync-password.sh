#!/bin/sh
set -e

# Roda no namespace de rede do container `database`.
# Conecta em 127.0.0.1 (trust no pg_hba do Postgres oficial) e alinha a senha com POSTGRES_PASSWORD.

_pass_sql=$(printf '%s' "${POSTGRES_PASSWORD}" | sed "s/'/''/g")

for _attempt in $(seq 1 30); do
  if pg_isready -h 127.0.0.1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

psql -h 127.0.0.1 -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -c "ALTER USER \"${POSTGRES_USER}\" WITH PASSWORD '${_pass_sql}';"

echo "[lex-pacs] Senha PostgreSQL sincronizada com POSTGRES_PASSWORD"
