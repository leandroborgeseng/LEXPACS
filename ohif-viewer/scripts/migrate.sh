#!/usr/bin/env bash
# Migrações de banco/dados entre versões LEX PACS.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -x "${SCRIPT_DIR}/migrate-e3.sh" ]; then
  "${SCRIPT_DIR}/migrate-e3.sh"
fi
