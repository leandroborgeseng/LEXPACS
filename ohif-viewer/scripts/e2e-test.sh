#!/usr/bin/env bash
# E2E Playwright — requer stack LEX PACS em execução (gateway :3000).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
E2E_DIR="${ROOT}/e2e"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:3000}"

if ! curl -sf "${GATEWAY_URL}/clinica/login" >/dev/null; then
  echo "Gateway indisponível em ${GATEWAY_URL}. Suba: cd ohif-viewer && docker compose up -d" >&2
  exit 1
fi

cd "${E2E_DIR}"
if [ ! -d node_modules/@playwright/test ]; then
  npm install --no-fund --no-audit
  npx playwright install chromium
fi

export GATEWAY_URL
npm test
