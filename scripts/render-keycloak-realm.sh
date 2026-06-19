#!/usr/bin/env sh
# Gera lex-pacs-realm.json a partir do template (URLs públicas do deploy).
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="${SCRIPT_DIR}/../ohif-viewer/keycloak/lex-pacs-realm.template.json"
OUTPUT="${1:-${SCRIPT_DIR}/../ohif-viewer/keycloak/lex-pacs-realm.rendered.json}"

LEX_PUBLIC_URL="${OHIF_VIEWER_URL:-http://localhost:3000}"
LEX_PUBLIC_URL="${LEX_PUBLIC_URL%/}"

KEYCLOAK_PUBLIC_URL="${KEYCLOAK_PUBLIC_URL:-}"
if [ -z "$KEYCLOAK_PUBLIC_URL" ]; then
  KEYCLOAK_PUBLIC_URL="${OIDC_PUBLIC_ISSUER_URL:-http://localhost:8080/realms/lex-pacs}"
  KEYCLOAK_PUBLIC_URL="${KEYCLOAK_PUBLIC_URL%/realms/lex-pacs}"
fi
KEYCLOAK_PUBLIC_URL="${KEYCLOAK_PUBLIC_URL%/}"

KEYCLOAK_SSL_REQUIRED="${KEYCLOAK_SSL_REQUIRED:-none}"
case "$LEX_PUBLIC_URL" in
  https://*) KEYCLOAK_SSL_REQUIRED="${KEYCLOAK_SSL_REQUIRED:-external}" ;;
esac

export LEX_PUBLIC_URL KEYCLOAK_PUBLIC_URL KEYCLOAK_SSL_REQUIRED OIDC_CLIENT_SECRET="${OIDC_CLIENT_SECRET:-lex-clinical-dev-secret}"

if ! command -v envsubst >/dev/null 2>&1; then
  echo "envsubst não encontrado (pacote gettext)" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT")"
envsubst '${LEX_PUBLIC_URL} ${KEYCLOAK_PUBLIC_URL} ${KEYCLOAK_SSL_REQUIRED} ${OIDC_CLIENT_SECRET}' \
  < "$TEMPLATE" > "$OUTPUT"
echo "Realm renderizado → $OUTPUT"
echo "  LEX_PUBLIC_URL=$LEX_PUBLIC_URL"
echo "  KEYCLOAK_PUBLIC_URL=$KEYCLOAK_PUBLIC_URL"
