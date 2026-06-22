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

# URLs internas — container → container (rede Docker)
internal_oidc="${OIDC_ISSUER_URL:-http://auth:8080/auth/realms/lex-pacs}"
if [[ "${internal_oidc}" == http://auth:* ]] || [[ "${internal_oidc}" == http://auth/* ]]; then
  echo "✓ OIDC_ISSUER_URL (rede Docker): ${internal_oidc}"
else
  echo "✗ OIDC_ISSUER_URL deve usar http://auth:8080/... (atual: ${internal_oidc})" >&2
  missing=1
fi

if [[ "${OIDC_PUBLIC_ISSUER_URL:-}" == http://auth:* ]]; then
  echo "✗ OIDC_PUBLIC_ISSUER_URL não pode apontar para auth:8080 (URL interna)" >&2
  missing=1
fi

orthanc_internal="${ORTHANC_URL:-http://server:8042}"
if [[ "${orthanc_internal}" == http://server:* ]] || [[ "${orthanc_internal}" == http://server/* ]]; then
  echo "✓ ORTHANC_URL (rede Docker): ${orthanc_internal}"
elif [ -n "${ORTHANC_URL:-}" ]; then
  echo "✗ ORTHANC_URL deve ser http://server:8042 (atual: ${orthanc_internal})" >&2
  missing=1
fi

if [ "${PORTAL_JWT_SECRET:-change-me-in-production}" = "change-me-in-production" ]; then
  echo "✗ PORTAL_JWT_SECRET ainda é o valor padrão inseguro" >&2
  missing=1
fi

if [ "${1:-}" = "--tls" ]; then
  echo
  echo "Modo TLS standalone (docker-compose.tls.yml)…"
  require LEX_PACS_DOMAIN
  require LETSENCRYPT_EMAIL
  if [[ "${OHIF_VIEWER_URL:-}" != https://* ]]; then
    echo "✗ OHIF_VIEWER_URL deve começar com https:// em produção TLS" >&2
    missing=1
  else
    echo "✓ OHIF_VIEWER_URL (HTTPS)"
  fi
  domain="${LEX_PACS_DOMAIN#https://}"
  domain="${domain#http://}"
  domain="${domain%%/*}"
  url_host="${OHIF_VIEWER_URL#https://}"
  url_host="${url_host%%/*}"
  if [ -n "${domain}" ] && [ -n "${url_host}" ] && [ "${domain}" != "${url_host}" ]; then
    echo "✗ LEX_PACS_DOMAIN (${domain}) difere de OHIF_VIEWER_URL (${url_host})" >&2
    missing=1
  else
    echo "✓ domínio consistente com OHIF_VIEWER_URL"
  fi
fi

if [ "${missing}" -ne 0 ]; then
  echo >&2
  echo "Corrija as variáveis acima. Ver .env.coolify.example e docs/COOLIFY.md" >&2
  exit 1
fi

echo "Ambiente OK para deploy."
