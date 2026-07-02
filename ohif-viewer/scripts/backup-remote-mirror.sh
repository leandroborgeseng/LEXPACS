#!/bin/sh
# Espelha o diretório de backups local para destino remoto (volume montado ou S3).
# Executar após backup-volumes.sh + backup-retention.sh.
set -eu

BACKUP_ROOT="${1:-${BACKUP_ROOT:-./backups}}"
BACKUP_REMOTE_DIR="${BACKUP_REMOTE_DIR:-}"
BACKUP_S3_BUCKET="${BACKUP_S3_BUCKET:-}"
BACKUP_S3_PREFIX="${BACKUP_S3_PREFIX:-lex-pacs}"
AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-}"
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-auto}"

if [ ! -d "${BACKUP_ROOT}" ]; then
  echo "Mirror: backup root inexistente (${BACKUP_ROOT})" >&2
  exit 1
fi

backup_mount_for_docker() {
  root="$1"
  if [ ! -f /.dockerenv ] || ! command -v docker >/dev/null 2>&1; then
    printf 'bind:%s' "${root}"
    return
  fi
  vol=$(docker inspect "$(hostname)" --format '{{range .Mounts}}{{if eq .Destination "/backups"}}{{.Name}}{{end}}{{end}}' 2>/dev/null || true)
  if [ -n "${vol}" ] && [ "${root}" = "/backups" ]; then
    printf 'vol:%s' "${vol}"
    return
  fi
  printf 'bind:%s' "${root}"
}

mirror_remote_dir() {
  [ -n "${BACKUP_REMOTE_DIR}" ] || return 0
  mkdir -p "${BACKUP_REMOTE_DIR}"
  echo "Mirror → ${BACKUP_REMOTE_DIR}"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "${BACKUP_ROOT}/" "${BACKUP_REMOTE_DIR}/"
  else
    find "${BACKUP_REMOTE_DIR}" -mindepth 1 -maxdepth 1 ! -name '.*' -exec rm -rf {} + 2>/dev/null || true
    cp -a "${BACKUP_ROOT}/." "${BACKUP_REMOTE_DIR}/"
  fi
}

mirror_s3() {
  [ -n "${BACKUP_S3_BUCKET}" ] || return 0
  if [ -z "${AWS_ACCESS_KEY_ID:-}" ] || [ -z "${AWS_SECRET_ACCESS_KEY:-}" ]; then
    echo "Mirror S3: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY ausentes" >&2
    return 1
  fi
  dest="s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX%/}/"
  echo "Mirror → ${dest}"
  mount=$(backup_mount_for_docker "${BACKUP_ROOT}")
  endpoint_args=""
  if [ -n "${AWS_ENDPOINT_URL}" ]; then
    endpoint_args="--endpoint-url ${AWS_ENDPOINT_URL}"
  fi
  case "${mount}" in
    vol:*)
      vol="${mount#vol:}"
      # shellcheck disable=SC2086
      docker run --rm \
        -v "${vol}:/backups:ro" \
        -e AWS_ACCESS_KEY_ID \
        -e AWS_SECRET_ACCESS_KEY \
        -e AWS_DEFAULT_REGION \
        amazon/aws-cli:2.15.0 \
        s3 sync /backups/ "${dest}" --delete ${endpoint_args}
      ;;
    bind:*)
      root="${mount#bind:}"
      # shellcheck disable=SC2086
      docker run --rm \
        -v "${root}:/backups:ro" \
        -e AWS_ACCESS_KEY_ID \
        -e AWS_SECRET_ACCESS_KEY \
        -e AWS_DEFAULT_REGION \
        amazon/aws-cli:2.15.0 \
        s3 sync /backups/ "${dest}" --delete ${endpoint_args}
      ;;
  esac
}

if [ -z "${BACKUP_REMOTE_DIR}" ] && [ -z "${BACKUP_S3_BUCKET}" ]; then
  exit 0
fi

mirror_remote_dir
mirror_s3
echo "Mirror remoto concluído."
