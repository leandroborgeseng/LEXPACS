#!/usr/bin/env bash
# Valida conectividade na rede Docker do LEX PACS.
# Container → container deve usar nomes de serviço (server, portal, auth, database).
# OHIF_VIEWER_URL é só para o navegador (redirects OIDC/cookies), nunca para chamadas internas.
#
# Uso:
#   ./scripts/check-docker-network.sh
#   GATEWAY_URL=http://leandroborges.eng.br ./scripts/check-docker-network.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:3000}"

PASS=0
FAIL=0
WARN=0

ok()   { echo "  ✓ $1"; PASS=$((PASS + 1)); }
bad()  { echo "  ✗ $1"; FAIL=$((FAIL + 1)); }
warn() { echo "  ⚠ $1"; WARN=$((WARN + 1)); }

echo "══════════════════════════════════════════"
echo " LEX PACS — rede Docker (interna)"
echo " Gateway público esperado: ${GATEWAY_URL}"
echo "══════════════════════════════════════════"
echo

echo "▶ Containers"
for c in gateway portal web-viewer server database auth; do
  if docker ps --format '{{.Names}}' | grep -qx "$c"; then
    ok "Container ${c} em execução"
  else
    bad "Container ${c} não está rodando"
  fi
done
echo

echo "▶ Portal → backends (rede Docker)"
if docker exec portal curl -sf http://server:8042/system >/dev/null 2>&1; then
  ok "portal → server:8042 (Orthanc)"
else
  bad "portal não alcança server:8042"
fi

auth_code=$(docker exec portal curl -s -o /dev/null -w '%{http_code}' http://auth:8080/auth/realms/lex-pacs 2>/dev/null || echo "000")
if [ "$auth_code" = "200" ]; then
  ok "portal → auth:8080 (Keycloak)"
else
  bad "portal → auth:8080 retornou ${auth_code}"
fi

if docker exec portal python3 -c "import socket; s=socket.create_connection(('database',5432),5); s.close()" 2>/dev/null; then
  ok "portal → database:5432 (PostgreSQL)"
else
  bad "portal não alcança database:5432"
fi
echo

echo "▶ Gateway → serviços internos"
if docker exec gateway wget -qO- http://portal:8080/api/health 2>/dev/null | grep -q '"status"'; then
  ok "gateway → portal:8080"
else
  bad "gateway não alcança portal:8080"
fi

if docker exec gateway wget -qO- http://web-viewer:80/ 2>/dev/null | grep -qi doctype; then
  ok "gateway → web-viewer:80"
else
  bad "gateway não alcança web-viewer:80"
fi

if docker exec gateway wget -qO- http://server:8042/system 2>/dev/null | grep -q '"Name"'; then
  ok "gateway → server:8042"
else
  bad "gateway não alcança server:8042"
fi

auth_gw=$(docker exec gateway wget -qO- --server-response http://auth:8080/auth/realms/lex-pacs 2>&1 | awk '/HTTP\// {code=$2} END {print code}')
if [ "${auth_gw:-}" = "200" ]; then
  ok "gateway → auth:8080"
else
  bad "gateway → auth:8080 retornou ${auth_gw:-?}"
fi
echo

echo "▶ Variáveis do portal (interno vs público)"
if docker ps --format '{{.Names}}' | grep -qx portal; then
  mapfile -t env_lines < <(docker exec portal printenv | grep -E '^(ORTHANC_URL|OIDC_ISSUER_URL|OIDC_PUBLIC_ISSUER_URL|OHIF_VIEWER_URL)=' | sort)
  for line in "${env_lines[@]}"; do
    echo "    ${line}"
  done

  orthanc_url=$(docker exec portal printenv ORTHANC_URL 2>/dev/null || true)
  oidc_internal=$(docker exec portal printenv OIDC_ISSUER_URL 2>/dev/null || true)
  oidc_public=$(docker exec portal printenv OIDC_PUBLIC_ISSUER_URL 2>/dev/null || true)
  ohif_public=$(docker exec portal printenv OHIF_VIEWER_URL 2>/dev/null || true)

  case "${orthanc_url:-}" in
    http://server:*|http://server/*) ok "ORTHANC_URL usa host Docker interno" ;;
    *) bad "ORTHANC_URL deve ser http://server:8042 (atual: ${orthanc_url:-?})" ;;
  esac

  case "${oidc_internal:-}" in
    http://auth:*|http://auth/*) ok "OIDC_ISSUER_URL usa auth na rede Docker" ;;
    *) bad "OIDC_ISSUER_URL deve ser http://auth:8080/... (atual: ${oidc_internal:-?})" ;;
  esac

  if [[ "${oidc_public:-}" == http://auth:* ]]; then
    bad "OIDC_PUBLIC_ISSUER_URL não pode ser URL interna (auth:8080)"
  elif [ -n "${oidc_public:-}" ]; then
    ok "OIDC_PUBLIC_ISSUER_URL definida para o navegador"
  else
    warn "OIDC_PUBLIC_ISSUER_URL vazia (será derivada de OHIF_VIEWER_URL)"
  fi

  gw_host="${GATEWAY_URL#http://}"
  gw_host="${gw_host#https://}"
  gw_host="${gw_host%%/*}"
  ohif_host="${ohif_public#http://}"
  ohif_host="${ohif_host#https://}"
  ohif_host="${ohif_host%%/*}"

  if [[ "${ohif_public:-}" == *localhost* ]] && [[ "${GATEWAY_URL:-}" != *localhost* ]]; then
    warn "OHIF_VIEWER_URL=${ohif_public} mas GATEWAY_URL=${GATEWAY_URL} — redirects OIDC/callback podem falhar"
    warn "Ajuste OHIF_VIEWER_URL no .env.coolify para coincidir com a URL do navegador"
  elif [ -n "${gw_host}" ] && [ -n "${ohif_host}" ] && [ "$gw_host" != "$ohif_host" ]; then
    warn "Host de OHIF_VIEWER_URL (${ohif_host}) difere de GATEWAY_URL (${gw_host})"
  else
    ok "OHIF_VIEWER_URL alinhada com GATEWAY_URL"
  fi
else
  bad "Portal não está rodando — não foi possível inspecionar env"
fi
echo

echo "▶ Tráfego que NÃO deve sair para internet (container → container)"
echo "    portal → server, auth, database"
echo "    gateway → portal, web-viewer, server, auth"
echo "    server → database"
echo "    auth-realm-init → volume (sem rede externa após build do realm)"
echo

echo "▶ Tráfego esperado via navegador (domínio público → gateway)"
health=$(curl -sf "${GATEWAY_URL}/paciente-api/health" 2>/dev/null || true)
if echo "$health" | grep -q '"status"'; then
  ok "Gateway acessível em ${GATEWAY_URL}"
else
  warn "Gateway não respondeu em ${GATEWAY_URL} (pode ser proxy externo ou stack parada)"
fi
echo

echo "══════════════════════════════════════════"
echo " Resultado: ${PASS} ok | ${FAIL} falha | ${WARN} aviso"
echo "══════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  echo "Ver docs/REDE-DOCKER.md" >&2
  exit 1
fi

exit 0
