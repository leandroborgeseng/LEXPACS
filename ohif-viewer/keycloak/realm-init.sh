#!/bin/sh
# Gera lex-pacs-realm.json a partir do template (Coolify / compose).
set -eu

TEMPLATE="/template/lex-pacs-realm.template.json"
OUTPUT="/output/lex-pacs-realm.json"

if [ ! -f "${TEMPLATE}" ]; then
  echo "ERRO: template ausente (${TEMPLATE})" >&2
  ls -la /template 2>/dev/null >&2 || true
  exit 1
fi

if [ ! -d /output ]; then
  echo "ERRO: volume /output não montado" >&2
  exit 1
fi

LEX_PUBLIC_URL=$(echo "${OHIF_VIEWER_URL:-http://localhost:3000}" | sed 's:/*$::')
KC_PATH=${KEYCLOAK_HTTP_RELATIVE_PATH:-/auth}
KC_PATH=$(echo "${KC_PATH}" | sed 's:/*$::')
KEYCLOAK_PUBLIC_URL=${KEYCLOAK_PUBLIC_URL:-${LEX_PUBLIC_URL}${KC_PATH}}
OIDC_PUBLIC_ISSUER_URL=${OIDC_PUBLIC_ISSUER_URL:-${LEX_PUBLIC_URL}${KC_PATH}/realms/lex-pacs}

export LEX_PUBLIC_URL KEYCLOAK_PUBLIC_URL OIDC_CLIENT_SECRET KEYCLOAK_SSL_REQUIRED

echo "OIDC público: ${OIDC_PUBLIC_ISSUER_URL}"
case "${LEX_PUBLIC_URL}" in
  https://*) export KEYCLOAK_SSL_REQUIRED=${KEYCLOAK_SSL_REQUIRED:-external} ;;
esac

if ! envsubst '${LEX_PUBLIC_URL} ${KEYCLOAK_PUBLIC_URL} ${KEYCLOAK_SSL_REQUIRED} ${OIDC_CLIENT_SECRET}' \
  < "${TEMPLATE}" > "${OUTPUT}"; then
  echo "ERRO: envsubst falhou ao renderizar o realm" >&2
  exit 1
fi

if [ ! -s "${OUTPUT}" ]; then
  echo "ERRO: ${OUTPUT} vazio após renderização" >&2
  exit 1
fi

echo "Realm OIDC gerado para ${LEX_PUBLIC_URL}"
