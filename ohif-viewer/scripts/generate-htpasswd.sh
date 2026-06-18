#!/bin/sh
# Uso: ./scripts/generate-htpasswd.sh [usuario] [senha]
USER="${1:-clinica}"
PASS="${2:-lexclinica2024}"
OUT="$(dirname "$0")/../nginx/.htpasswd"
printf '%s:%s\n' "$USER" "$(openssl passwd -apr1 "$PASS")" > "$OUT"
echo "Gerado: $OUT (usuário: $USER)"
