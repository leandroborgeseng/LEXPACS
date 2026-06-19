#!/usr/bin/env bash
# Valida variáveis mínimas antes do deploy Coolify / produção.
set -euo pipefail

missing=0
require() {
  local name=$1
  if [ -z "${!name:-}" ]; then
    echo "✗ ${name} não definida" >&2
    missing=1
  else
    echo "✓ ${name}"
  fi
}

echo "Validando ambiente LEX PACS (Coolify/produção)…"
require OHIF_VIEWER_URL
require PORTAL_JWT_SECRET
require POSTGRES_PASSWORD
require OIDC_CLIENT_SECRET
require KEYCLOAK_ADMIN_PASSWORD

if [ -z "${OIDC_PUBLIC_ISSUER_URL:-}" ]; then
  base="${OHIF_VIEWER_URL%/}"
  OIDC_PUBLIC_ISSUER_URL="${base}/auth/realms/lex-pacs"
  echo "→ OIDC_PUBLIC_ISSUER_URL derivada: ${OIDC_PUBLIC_ISSUER_URL}"
else
  echo "✓ OIDC_PUBLIC_ISSUER_URL"
fi

if [ "${PORTAL_JWT_SECRET:-change-me-in-production}" = "change-me-in-production" ]; then
  echo "✗ PORTAL_JWT_SECRET ainda é o valor padrão inseguro" >&2
  missing=1
fi

if [ "${missing}" -ne 0 ]; then
  echo >&2
  echo "Corrija as variáveis acima. Ver .env.coolify.example e docs/COOLIFY.md" >&2
  exit 1
fi

echo "Ambiente OK para deploy."
