#!/usr/bin/env bash
# Corrige usuários OIDC após import do realm (dev).
set -euo pipefail

KC_URL="${KEYCLOAK_URL:-http://localhost:3000/auth}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
REALM="${KEYCLOAK_REALM:-lex-pacs}"

for _ in $(seq 1 30); do
  if curl -fsS "${KC_URL}/realms/${REALM}" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

token=$(curl -s -X POST "${KC_URL}/realms/master/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=admin-cli" \
  -d "username=${ADMIN_USER}" \
  -d "password=${ADMIN_PASS}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

if [ -z "$token" ]; then
  echo "keycloak-init: não foi possível autenticar no master" >&2
  exit 1
fi

for user in radiologista tecnico admin; do
  uid=$(curl -s -H "Authorization: Bearer ${token}" \
    "${KC_URL}/admin/realms/${REALM}/users?username=${user}" | \
    python3 -c "import sys,json; u=json.load(sys.stdin); print(u[0]['id'] if u else '')")
  [ -n "$uid" ] || continue
  curl -s -X PUT -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    "${KC_URL}/admin/realms/${REALM}/users/${uid}" \
    -d '{"requiredActions":[],"emailVerified":true,"enabled":true}' >/dev/null
done

echo "keycloak-init: usuários OIDC prontos"
