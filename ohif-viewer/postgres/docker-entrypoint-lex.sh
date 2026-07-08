#!/bin/sh
set -e

# Sincroniza POSTGRES_PASSWORD após o Postgres subir (socket Unix / local trust).
if [ "$1" = 'postgres' ]; then
  (
    for _attempt in $(seq 1 90); do
      if pg_isready -U "${POSTGRES_USER:-orthanc}" -d "${POSTGRES_DB:-orthanc}" >/dev/null 2>&1; then
        /usr/local/bin/lex-sync-password.sh || echo "[lex-pacs] Aviso: sync de senha falhou (tentativa ${_attempt})" >&2
        break
      fi
      sleep 1
    done
  ) &
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
