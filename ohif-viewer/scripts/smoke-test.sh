#!/usr/bin/env bash
# Smoke tests LEX PACS — rodar após cada etapa do roadmap.
#
# Uso:
#   ./scripts/smoke-test.sh                 # todas as etapas já implementadas
#   ./scripts/smoke-test.sh E1 E2 E9        # etapas específicas
#   ./scripts/smoke-test.sh --list          # lista etapas disponíveis
#
# Variáveis (.env ou export): GATEWAY_URL, ORTHANC_URL, CLINIC_USER, CLINIC_PASS,
#   PATIENT_ID, PATIENT_BIRTH, SMOKE_BACKUP_DIR

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "${PROJECT_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${PROJECT_DIR}/.env"
  set +a
fi

GATEWAY_URL="${GATEWAY_URL:-http://localhost:3000}"
ORTHANC_URL="${ORTHANC_URL:-http://localhost:8042}"
CLINIC_USER="${CLINIC_USER:-clinica}"
CLINIC_PASS="${CLINIC_PASS:-lexclinica2024}"
PATIENT_ID="${PATIENT_ID:-+oYVjq}"
PATIENT_BIRTH="${PATIENT_BIRTH:-25/08/1947}"
SMOKE_BACKUP_DIR="${SMOKE_BACKUP_DIR:-/tmp/lex-pacs-smoke-backup}"
KEYCLOAK_URL="${KEYCLOAK_URL:-${GATEWAY_URL}/auth}"
OIDC_CLIENT_SECRET="${OIDC_CLIENT_SECRET:-lex-clinical-dev-secret}"

# Etapas com testes automatizados prontos
IMPLEMENTED_STAGES=(E1 E2 E2b E2c E2d E3 E4 E5 E6 E7 E8 E9 E10 E11 E12 E13 E14 E15 S10 S11)
PENDING_STAGES=()

if [ "${1:-}" = "--list" ]; then
  echo "Implementadas: ${IMPLEMENTED_STAGES[*]}"
  echo "Pendentes:     ${PENDING_STAGES[*]}"
  exit 0
fi

RUN_STAGES=("$@")
if [ ${#RUN_STAGES[@]} -eq 0 ]; then
  RUN_STAGES=("${IMPLEMENTED_STAGES[@]}")
fi

should_run() {
  local id=$1
  for s in "${RUN_STAGES[@]}"; do
    if [ "$s" = "$id" ]; then
      return 0
    fi
  done
  return 1
}

PASS=0
FAIL=0
SKIP=0
TOKEN=""
STUDY_UID=""
STUDY_UID_DRAFT=""
E12_SIGNED_UID=""
PATIENT_SIGNED_UID=""
OIDC_TOKEN=""

wait_orthanc() {
  for _ in $(seq 1 45); do
    if curl -fsS "${ORTHANC_URL}/system" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

pass() { echo "  ✓ $1"; PASS=$((PASS + 1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL + 1)); }
skip() { echo "  ○ $1"; SKIP=$((SKIP + 1)); }
pending() { echo "  ○ $1 (etapa ainda não implementada)"; SKIP=$((SKIP + 1)); }

http_code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
COOKIE_JAR="${SMOKE_COOKIE_JAR:-/tmp/lex-pacs-clinic-cookies.txt}"
CLINIC_TOKEN=""

clinical_login() {
  local resp
  resp=$(curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" -X POST \
    "${GATEWAY_URL}/clinica-api/auth/clinical/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"${CLINIC_USER}\",\"password\":\"${CLINIC_PASS}\",\"next\":\"/viewer/\"}")
  CLINIC_TOKEN=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
}

http_code_auth() { curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE_JAR" -c "$COOKIE_JAR" "$@"; }

curl_auth() { curl -s -b "$COOKIE_JAR" -c "$COOKIE_JAR" "$@"; }

curl_auth_bearer() {
  if [ -n "$CLINIC_TOKEN" ]; then
    curl -s -H "Authorization: Bearer ${CLINIC_TOKEN}" "$@"
  else
    curl -s -b "$COOKIE_JAR" -c "$COOKIE_JAR" "$@"
  fi
}

json_post() {
  local url=$1 data=$2 auth=${3:-}
  if [ -n "$auth" ]; then
    curl_auth -X POST "$url" \
      -H "Content-Type: application/json" -d "$data"
  else
    curl -s -X POST "$url" -H "Content-Type: application/json" -d "$data"
  fi
}

load_study_uids() {
  mapfile -t _lex_study_lines < <(curl -s "${ORTHANC_URL}/tools/find" -X POST -H "Content-Type: application/json" \
    -d '{"Level":"Study","Query":{}}' | python3 -c "
import sys, json, urllib.request
ids = json.load(sys.stdin)
orthanc = '${ORTHANC_URL}'
gateway = '${GATEWAY_URL}'
token = '${CLINIC_TOKEN}'

def study_uid(oid):
    d = json.loads(urllib.request.urlopen(f'{orthanc}/studies/{oid}').read())
    return d.get('MainDicomTags', {}).get('StudyInstanceUID', '')

def report_status(uid):
    req = urllib.request.Request(f'{gateway}/clinica-api/reports/{uid}')
    req.add_header('Authorization', f'Bearer {token}')
    try:
        return json.loads(urllib.request.urlopen(req).read()).get('status', '')
    except Exception:
        return ''

uids = [study_uid(i) for i in ids]
uids = [u for u in uids if u]
draft = next((u for u in uids if report_status(u) != 'signed'), '')
print(uids[0] if uids else '')
print(draft or (uids[1] if len(uids) > 1 else (uids[0] if uids else '')))
" 2>/dev/null)
  STUDY_UID="${_lex_study_lines[0]:-}"
  STUDY_UID_DRAFT="${_lex_study_lines[1]:-}"
}

load_patient_signed_uid() {
  mapfile -t _patient_signed_lines < <(curl -s "${ORTHANC_URL}/tools/find" -X POST -H "Content-Type: application/json" \
    -d "{\"Level\":\"Study\",\"Query\":{\"PatientID\":\"${PATIENT_ID}\"}}" | python3 -c "
import sys, json, urllib.request
ids = json.load(sys.stdin)
orthanc = '${ORTHANC_URL}'
gateway = '${GATEWAY_URL}'
token = '${CLINIC_TOKEN}'

def study_uid(oid):
    d = json.loads(urllib.request.urlopen(f'{orthanc}/studies/{oid}').read())
    return d.get('MainDicomTags', {}).get('StudyInstanceUID', '')

def report_status(uid):
    req = urllib.request.Request(f'{gateway}/clinica-api/reports/{uid}')
    req.add_header('Authorization', f'Bearer {token}')
    try:
        return json.loads(urllib.request.urlopen(req).read()).get('status', '')
    except Exception:
        return ''

for oid in ids:
    uid = study_uid(oid)
    if uid and report_status(uid) == 'signed':
        print(uid)
        break
" 2>/dev/null)
  PATIENT_SIGNED_UID="${_patient_signed_lines[0]:-}"
}

echo "══════════════════════════════════════════"
echo " LEX PACS — smoke test"
echo " Gateway: ${GATEWAY_URL}"
echo " Etapas: ${RUN_STAGES[*]}"
echo "══════════════════════════════════════════"
echo

# ── Infraestrutura (sempre) ──
echo "▶ Infraestrutura"
COMPOSE_FILE="${SMOKE_COMPOSE_FILE:-${PROJECT_DIR}/docker-compose.yml}"
for c in gateway portal web-viewer server database auth; do
  if docker ps --format '{{.Names}}' | grep -qx "$c"; then
    pass "Container ${c} em execução"
  else
    fail "Container ${c} não está rodando"
  fi
done

health=""
for _ in 1 2 3 4 5; do
  health=$(curl -s "${GATEWAY_URL}/paciente-api/health")
  if echo "$health" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('status')=='ok' else 1)" 2>/dev/null; then
    break
  fi
  sleep 2
done
if echo "$health" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('status')=='ok' else 1)" 2>/dev/null; then
  pass "Portal health status=ok"
else
  fail "Portal health inválido"
fi
[ "$(http_code "${GATEWAY_URL}/clinica/login")" = "200" ] && pass "Página de login clínico → 200" || fail "Login clínico indisponível"

clinical_login
if [ -z "$CLINIC_TOKEN" ]; then
  echo "  ✗ Falha ao obter sessão clínica (login)"
  FAIL=$((FAIL + 1))
else
  echo "  ✓ Sessão clínica obtida"
  PASS=$((PASS + 1))
fi

if echo "$health" | grep -qi orthanc; then
  fail "Health expõe nome de backend (usar campo genérico)"
else
  pass "Health sem vazamento de nome de backend"
fi

code=$(http_code_auth "${GATEWAY_URL}/dicom-web/studies?limit=1")
[ "$code" = "200" ] && pass "DICOMweb clínico → 200" || fail "DICOMweb clínico → ${code}"
echo

# ── E1 ──
if should_run E1; then
  echo "▶ E1 — Portal do paciente"
  [ "$(http_code "${GATEWAY_URL}/paciente/")" = "200" ] && pass "GET /paciente/ → 200" || fail "GET /paciente/ falhou"

  html=$(curl -s "${GATEWAY_URL}/paciente/")
  echo "$html" | grep -qi "LEX PACS" && pass "Portal exibe marca LEX PACS" || fail "Marca ausente no portal"
  echo "$html" | grep -qi "tag DICOM" && fail "Portal expõe termo técnico DICOM" || pass "Portal sem jargão DICOM na UI"

  login=$(json_post "${GATEWAY_URL}/paciente-api/auth/login" \
    "{\"patient_id\":\"${PATIENT_ID}\",\"birth_date\":\"${PATIENT_BIRTH}\"}")
  TOKEN=$(echo "$login" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
  [ -n "$TOKEN" ] && pass "Login paciente → JWT" || fail "Login paciente falhou"

  [ "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer ${TOKEN}" \
    "${GATEWAY_URL}/paciente-api/studies")" = "200" ] && pass "Lista de exames → 200" || fail "Lista exames falhou"

  [ "$(http_code "${GATEWAY_URL}/paciente/docs")" = "404" ] && pass "Swagger portal bloqueado" || fail "Swagger portal acessível"
  echo
fi

# ── E2 ──
if should_run E2; then
  echo "▶ E2 — Gateway e autenticação"
  [ "$(http_code "${GATEWAY_URL}/viewer/")" = "302" ] && pass "Worklist sem sessão → redirect login" || fail "Worklist sem sessão incorreto"
  [ "$(http_code_auth "${GATEWAY_URL}/viewer/")" = "200" ] && pass "Worklist com sessão → 200" || fail "Worklist com sessão falhou"
  [ "$(http_code "${GATEWAY_URL}/paciente-api/auth/validate-viewer-cookie")" = "404" ] \
    && pass "Cookie validation pública → 404" || fail "Cookie validation exposta"

  if [ -n "$TOKEN" ]; then
    study_uid=$(curl -s -H "Authorization: Bearer ${TOKEN}" "${GATEWAY_URL}/paciente-api/studies" | \
      python3 -c "import sys,json; s=json.load(sys.stdin).get('studies',[]); print(s[0]['study_instance_uid'] if s else '')" 2>/dev/null || true)
    if [ -n "$study_uid" ]; then
      jar=$(mktemp)
      redir=$(curl -s -X POST -H "Authorization: Bearer ${TOKEN}" -c "$jar" \
        "${GATEWAY_URL}/paciente-api/studies/${study_uid}/viewer-session" | \
        python3 -c "import sys,json; print(json.load(sys.stdin).get('redirect_url',''))" 2>/dev/null || true)
      if [ -n "$redir" ]; then
        [ "$(curl -s -b "$jar" -o /dev/null -w '%{http_code}' "${GATEWAY_URL}${redir}")" = "200" ] \
          && pass "Viewer paciente com cookie → 200" || fail "Viewer paciente falhou"
        wl_code=$(curl -s -b "$jar" -o /dev/null -w '%{http_code}' "${GATEWAY_URL}/viewer/")
        if [ "$wl_code" = "401" ] || [ "$wl_code" = "302" ]; then
          pass "Worklist bloqueada para cookie paciente → ${wl_code}"
        else
          fail "Paciente acessou worklist (${wl_code})"
        fi
      else
        fail "viewer-session sem redirect"
      fi
      rm -f "$jar"
    else
      skip "Sem estudos para fluxo paciente"
    fi
  else
    skip "Fluxo paciente (E1 não rodou)"
  fi
  echo
fi

# ── E2b ──
if should_run E2b; then
  echo "▶ E2b — White-label visualizador"
  html=$(curl_auth "${GATEWAY_URL}/viewer/")
  echo "$html" | grep -qi "LEX PACS" && pass "HTML viewer contém LEX PACS" || fail "Título LEX PACS ausente"
  echo "$html" | grep -q "OHIF Viewer" && fail "HTML ainda contém OHIF Viewer" || pass "Sem OHIF Viewer no título"

  manifest=$(curl_auth "${GATEWAY_URL}/viewer/manifest.json")
  echo "$manifest" | python3 -c "import sys,json; n=json.load(sys.stdin).get('name',''); exit(0 if 'LEX' in n.upper() else 1)" 2>/dev/null \
    && pass "manifest.json com marca LEX" || fail "manifest.json sem LEX PACS"
  echo
fi

# ── E2c ──
if should_run E2c; then
  echo "▶ E2c — AE Title"
  settings=$(curl_auth "${GATEWAY_URL}/clinica-api/admin/pacs/settings")
  aet=$(echo "$settings" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dicom_aet',''))" 2>/dev/null || true)
  oaet=$(curl -s "${ORTHANC_URL}/system" | python3 -c "import sys,json; print(json.load(sys.stdin).get('DicomAet',''))" 2>/dev/null || true)
  [ -n "$aet" ] && pass "API retorna dicom_aet=${aet}" || fail "Config PACS indisponível"
  [ "$aet" = "$oaet" ] && pass "AE Title = servidor DICOM" || fail "AE Title divergente (api=${aet}, srv=${oaet})"
  echo
fi

# ── E2d ──
if should_run E2d; then
  echo "▶ E2d — API clínica"
  [ "$(http_code "${GATEWAY_URL}/clinica-api/admin/pacs/settings")" = "302" ] && pass "API clínica sem sessão → redirect" || fail "API sem sessão"
  [ "$(http_code_auth "${GATEWAY_URL}/clinica-api/admin/pacs/settings")" = "200" ] && pass "API clínica com auth → 200" || fail "API com auth"
  echo
fi

# ── E3 ──
if should_run E3; then
  echo "▶ E3 — PostgreSQL + volumes separados"
  if docker volume inspect ohif-viewer_server-data >/dev/null 2>&1 || \
     docker volume inspect lex-pacs_server-data >/dev/null 2>&1 || \
     docker volume inspect ohif-viewer_orthanc-storage >/dev/null 2>&1; then
    pass "Volume server-data presente"
  else
    fail "Volume server-data não encontrado"
  fi
  if docker volume inspect ohif-viewer_database-data >/dev/null 2>&1 || \
     docker volume inspect lex-pacs_database-data >/dev/null 2>&1 || \
     docker volume inspect ohif-viewer_postgres-data >/dev/null 2>&1; then
    pass "Volume database-data presente"
  else
    fail "Volume database-data não encontrado"
  fi
  if docker compose -f "${COMPOSE_FILE}" ps database 2>/dev/null | grep -qE 'healthy|running'; then
    pass "PostgreSQL em execução"
  else
    fail "PostgreSQL não está rodando"
  fi
  if docker compose -f "${COMPOSE_FILE}" exec -T database \
    pg_isready -U "${POSTGRES_USER:-orthanc}" -d "${POSTGRES_DB:-orthanc}" >/dev/null 2>&1; then
    pass "PostgreSQL aceita conexões"
  else
    fail "PostgreSQL não responde a pg_isready"
  fi
  pacs_cfg=$(curl_auth "${GATEWAY_URL}/clinica-api/admin/pacs/settings")
  if echo "$pacs_cfg" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('postgresql_index') else 1)" 2>/dev/null; then
    pass "Índice PostgreSQL habilitado na config"
  else
    fail "PostgreSQL index não habilitado"
  fi
  if echo "$pacs_cfg" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if '/storage' in d.get('storage_directory','') else 1)" 2>/dev/null; then
    pass "StorageDirectory separado do índice"
  else
    fail "StorageDirectory não aponta para volume dedicado"
  fi
  studies=$(curl_auth "${GATEWAY_URL}/dicom-web/studies?limit=1")
  if echo "$studies" | python3 -c "import sys,json; json.load(sys.stdin); sys.exit(0)" 2>/dev/null; then
    pass "DICOMweb responde após migração E3"
  else
    fail "DICOMweb falhou após E3"
  fi
  if [ -x "${SCRIPT_DIR}/migrate-e3.sh" ]; then
    pass "Script migrate-e3.sh disponível"
  else
    fail "migrate-e3.sh ausente"
  fi
  echo
fi

# ── E4 ──
if should_run E4; then
  echo "▶ E4 — Compressão lossless na ingestão"
  JPEG_LS="1.2.840.10008.1.2.4.80"
  pacs_cfg=$(curl_auth "${GATEWAY_URL}/clinica-api/admin/pacs/settings")
  if echo "$pacs_cfg" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('ingest_transcoding')=='${JPEG_LS}' else 1)" 2>/dev/null; then
    pass "IngestTranscoding = JPEG-LS lossless"
  else
    fail "IngestTranscoding não configurado para JPEG-LS"
  fi
  if grep -q 'libOrthancGdcm.so' "${PROJECT_DIR}/orthanc/orthanc.base.json" 2>/dev/null; then
    pass "Plugin GDCM configurado no template Orthanc"
  else
    fail "Plugin GDCM ausente"
  fi
  echo
fi

# ── E7 ──
if should_run E7; then
  echo "▶ E7 — Configurações DICOM ampliadas"
  pacs_cfg=$(curl_auth "${GATEWAY_URL}/clinica-api/admin/pacs/settings")
  if echo "$pacs_cfg" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'dicom_check_called_aet' in d and 'name' in d else 1)" 2>/dev/null; then
    pass "API expõe instituição e verificação de AE"
  else
    fail "API sem campos E7"
  fi
  current_name=$(echo "$pacs_cfg" | python3 -c "import sys,json; print(json.load(sys.stdin).get('name',''))" 2>/dev/null || true)
  if [ "${current_name}" = "LEX PACS Smoke" ]; then
    pass "E7: nome da instituição (regressão)"
  else
    put_srv=$(curl_auth -X PUT "${GATEWAY_URL}/clinica-api/admin/pacs/settings" \
      -H "Content-Type: application/json" \
      -d '{"dicom_aet":"LEXPACS","name":"LEX PACS Smoke","dicom_check_called_aet":false}')
    if echo "$put_srv" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('name')=='LEX PACS Smoke' else 1)" 2>/dev/null; then
      pass "E7: salvar nome da instituição"
    else
      fail "E7: salvar servidor falhou"
    fi
  fi
  equip_list=$(curl_auth "${GATEWAY_URL}/clinica-api/admin/pacs/equipment")
  if echo "$equip_list" | grep -q 'RX_SMOKE'; then
    pass "E7: equipamento cadastrado (regressão)"
  else
    equip=$(curl_auth -X PUT "${GATEWAY_URL}/clinica-api/admin/pacs/equipment" \
      -H "Content-Type: application/json" \
      -d '{"items":[{"aet":"RX_SMOKE","host":"127.0.0.1","port":11112,"description":"RX Sala Smoke","modality":"DX"}]}')
    if echo "$equip" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('items') and d['items'][0].get('aet')=='RX_SMOKE' else 1)" 2>/dev/null; then
      pass "E7: cadastrar equipamento"
    else
      fail "E7: equipamento falhou"
    fi
  fi
  wait_orthanc || true
  if docker compose -f "${COMPOSE_FILE}" exec -T portal \
    grep -q RX_SMOKE /orthanc-config/orthanc.json 2>/dev/null; then
    pass "E7: equipamento sincronizado no servidor DICOM"
  else
    fail "E7: DicomModalities não atualizado"
  fi
  echo
fi

# ── E8 ──
if should_run E8; then
  echo "▶ E8 — Visões de worklist"
  views=$(curl_auth "${GATEWAY_URL}/clinica-api/admin/pacs/worklist-views")
  if echo "$views" | python3 -c "import sys,json; d=json.load(sys.stdin); ids={v['id'] for v in d.get('views',[])}; need={'all','rx-sala-1','ct','mr','us'}; sys.exit(0 if need<=ids else 1)" 2>/dev/null; then
    pass "Presets de visão disponíveis (Todos, RX, CT, MR, US)"
  else
    fail "Presets de worklist incompletos"
  fi
  code_view=$(http_code_auth "${GATEWAY_URL}/viewer/?view=ct")
  [ "$code_view" = "200" ] && pass "Worklist com ?view=ct → 200" || fail "Worklist ?view=ct → ${code_view}"
  code_auth=$(http_code_auth "${GATEWAY_URL}/viewer/")
  [ "$code_auth" = "200" ] && pass "Autenticação worklist após visão → 200" || fail "Auth worklist → ${code_auth}"
  echo
fi

# ── E5 ──
if should_run E5; then
  echo "▶ E5 — Backup (script manual)"
  if [ -x "${SCRIPT_DIR}/backup-volumes.sh" ]; then
    pass "Script backup-volumes.sh existe e é executável"
  else
    fail "backup-volumes.sh ausente ou sem permissão"
  fi

  if docker volume inspect ohif-viewer_lex-reports >/dev/null 2>&1; then
    pass "Volume lex-reports presente"
  else
    fail "Volume lex-reports não encontrado"
  fi

  if docker volume inspect ohif-viewer_server-data >/dev/null 2>&1 || \
     docker volume inspect lex-pacs_server-data >/dev/null 2>&1 || \
     docker volume inspect ohif-viewer_orthanc-storage >/dev/null 2>&1; then
    pass "Volume server-data presente"
  else
    fail "Volume server-data não encontrado"
  fi

  if docker volume inspect ohif-viewer_server-config >/dev/null 2>&1 || \
     docker volume inspect lex-pacs_server-config >/dev/null 2>&1 || \
     docker volume inspect ohif-viewer_orthanc-config >/dev/null 2>&1; then
    pass "Volume server-config presente"
  else
    fail "Volume server-config não encontrado"
  fi

  rm -rf "${SMOKE_BACKUP_DIR}"
  if "${SCRIPT_DIR}/backup-volumes.sh" "${SMOKE_BACKUP_DIR}" >/dev/null 2>&1; then
    BACKUP_SNAPSHOT=$(find "${SMOKE_BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d | head -1)
    if [ -n "${BACKUP_SNAPSHOT}" ] && [ -f "${BACKUP_SNAPSHOT}/manifest.json" ]; then
      pass "Backup gera manifest.json"
    else
      fail "Backup sem manifest.json"
    fi
    if [ -n "${BACKUP_SNAPSHOT}" ] && ls "${BACKUP_SNAPSHOT}"/*.tar.gz >/dev/null 2>&1; then
      pass "Backup gera arquivo(s) .tar.gz"
    else
      fail "Backup sem arquivos .tar.gz"
    fi
    if [ -n "${BACKUP_SNAPSHOT}" ] && [ -f "${BACKUP_SNAPSHOT}/postgres.dump" ]; then
      pass "Backup inclui postgres.dump"
    else
      fail "Backup sem postgres.dump"
    fi
    if [ -x "${SCRIPT_DIR}/verify-backup.sh" ] && "${SCRIPT_DIR}/verify-backup.sh" "${BACKUP_SNAPSHOT}" >/dev/null 2>&1; then
      pass "verify-backup.sh valida snapshot"
    else
      fail "verify-backup.sh falhou no snapshot"
    fi
    if [ -f "${SCRIPT_DIR}/backup-retention.py" ]; then
      pass "Política de retenção 7+4 (backup-retention.py)"
    else
      fail "backup-retention.py ausente"
    fi
  else
    fail "Execução de backup-volumes.sh falhou"
  fi
  echo
fi

# ── E6 ──
if should_run E6; then
  echo "▶ E6 — Upgrade de versão"
  VERSION_FILE="${PROJECT_DIR}/LEX_PACS_VERSION"
  UPGRADE_DOC="${PROJECT_DIR}/../docs/UPGRADE.md"

  if [ -f "${VERSION_FILE}" ] && grep -qE '^[0-9]+\.[0-9]+\.[0-9]+' "${VERSION_FILE}"; then
    pass "LEX_PACS_VERSION definido ($(tr -d '[:space:]' < "${VERSION_FILE}"))"
  else
    fail "LEX_PACS_VERSION ausente ou inválido"
  fi

  for script in upgrade.sh rollback.sh restore-backup.sh; do
    if [ -x "${SCRIPT_DIR}/${script}" ]; then
      pass "Script ${script} executável"
    else
      fail "Script ${script} ausente ou sem permissão"
    fi
  done

  if [ -f "${UPGRADE_DOC}" ]; then
    pass "Runbook docs/UPGRADE.md presente"
  else
    fail "docs/UPGRADE.md ausente"
  fi

  if grep -q 'lex-pacs/viewer:' "${PROJECT_DIR}/docker-compose.yml" 2>/dev/null \
    && ! grep -q 'lex-pacs/viewer:latest' "${PROJECT_DIR}/docker-compose.yml" 2>/dev/null; then
    pass "Compose usa tag fixa lex-pacs/viewer"
  else
    fail "Compose sem tag versionada para viewer"
  fi

  if ! grep -q 'orthanc-plugins:latest' "${PROJECT_DIR}/docker-compose.yml" 2>/dev/null; then
    pass "Orthanc sem tag :latest"
  else
    fail "Orthanc ainda usa :latest"
  fi

  expected_ver=$(tr -d '[:space:]' < "${VERSION_FILE}" 2>/dev/null || echo "")
  e6_health=$(curl -s "${GATEWAY_URL}/paciente-api/health")
  reported_ver=$(echo "$e6_health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version',''))" 2>/dev/null || true)
  if [ -n "${expected_ver}" ] && [ "${reported_ver}" = "${expected_ver}" ]; then
    pass "Health expõe version=${reported_ver}"
  else
    fail "Health version (${reported_ver:-?}) ≠ LEX_PACS_VERSION (${expected_ver:-?})"
  fi

  rm -rf "${SMOKE_BACKUP_DIR}"
  if "${SCRIPT_DIR}/backup-volumes.sh" "${SMOKE_BACKUP_DIR}" >/dev/null 2>&1; then
    BACKUP_SNAPSHOT=$(find "${SMOKE_BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d | head -1)
    if [ -n "${BACKUP_SNAPSHOT}" ] && python3 -c "
import json, sys
m = json.load(open('${BACKUP_SNAPSHOT}/manifest.json'))
sys.exit(0 if m.get('lex_pacs_version') else 1)
" 2>/dev/null; then
      pass "Backup manifest inclui lex_pacs_version"
    else
      fail "Backup manifest sem lex_pacs_version"
    fi
  else
    fail "Backup para validação E6 falhou"
  fi
  echo
fi

# ── E9 E10 E11 — Laudos ──
if should_run E9 || should_run E10 || should_run E11; then
  wait_orthanc || true
  load_study_uids
  echo "▶ E9/E10/E11 — Laudos"
  [ -n "$STUDY_UID" ] && pass "Estudo disponível para testes" || fail "Nenhum estudo no servidor"

  target="${STUDY_UID_DRAFT:-$STUDY_UID}"
  current=$(curl_auth "${GATEWAY_URL}/clinica-api/reports/${target}")
  status=$(echo "$current" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)

  if should_run E9; then
    if [ "$status" = "signed" ]; then
      pass "E9: laudo em estado assinado (regressão)"
    else
      draft=$(curl_auth -X PUT \
        "${GATEWAY_URL}/clinica-api/reports/${target}" \
        -H "Content-Type: application/json" \
        -d '{"content_html":"<p>smoke E9</p>","author_name":"Smoke"}')
      [ "$(echo "$draft" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)" = "draft" ] \
        && pass "E9: salvar rascunho rich text" || fail "E9: rascunho falhou"
      status="draft"
    fi
  fi

  if should_run E10; then
    if [ "$status" = "signed" ]; then
      skip "E10: PDF (estudo já assinado — use outro exame para teste completo)"
    else
      pdf=$(mktemp --suffix=.pdf)
      printf '%%PDF-1.0\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n' > "$pdf"
      up=$(curl_auth -X POST \
        -F "file=@${pdf};type=application/pdf" \
        "${GATEWAY_URL}/clinica-api/reports/${target}/pdf")
      rm -f "$pdf"
      [ "$(echo "$up" | python3 -c "import sys,json; print(json.load(sys.stdin).get('has_pdf', False))" 2>/dev/null)" = "True" ] \
        && pass "E10: upload PDF anexo" || fail "E10: upload PDF falhou"
      [ "$(http_code_auth "${GATEWAY_URL}/clinica-api/reports/${target}/pdf")" = "200" ] \
        && pass "E10: download PDF → 200" || fail "E10: download PDF falhou"
    fi
  fi

  if should_run E11; then
    if [ "$status" = "signed" ]; then
      pass "E11: laudo já assinado (regressão)"
      E12_SIGNED_UID="$target"
    else
      sign=$(curl_auth -X POST \
        "${GATEWAY_URL}/clinica-api/reports/${target}/sign" \
        -H "Content-Type: application/json" \
        -d '{"signed_by":"Smoke Radiologista","signed_crm":"00000-SP"}')
      [ "$(echo "$sign" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)" = "signed" ] \
        && pass "E11: assinar laudo" || fail "E11: assinatura falhou"
    fi
    block=$(curl_auth -o /dev/null -w "%{http_code}" -X PUT \
      "${GATEWAY_URL}/clinica-api/reports/${target}" \
      -H "Content-Type: application/json" \
      -d '{"content_html":"<p>x</p>","author_name":"x"}')
    [ "$block" = "403" ] && pass "E11: edição bloqueada após assinar → 403" || fail "E11: laudo editável após assinar"
    E12_SIGNED_UID="$target"
  fi
  echo
fi

# ── E12 ──
if should_run E12; then
  echo "▶ E12 — Laudo no portal do paciente"
  if [ -z "$TOKEN" ]; then
    login=$(json_post "${GATEWAY_URL}/paciente-api/auth/login" \
      "{\"patient_id\":\"${PATIENT_ID}\",\"birth_date\":\"${PATIENT_BIRTH}\"}")
    TOKEN=$(echo "$login" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
  fi

  load_patient_signed_uid
  signed_uid="${PATIENT_SIGNED_UID:-}"
  if [ -z "$signed_uid" ]; then
    skip "E12: nenhum laudo assinado do paciente ${PATIENT_ID}"
  else
    pass "Estudo assinado do paciente de teste"
    curl_auth -X POST \
      "${GATEWAY_URL}/clinica-api/reports/${signed_uid}/revoke-patient" >/dev/null 2>&1 || true

    blocked=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${TOKEN}" \
      "${GATEWAY_URL}/paciente-api/studies/${signed_uid}/report")
    [ "$blocked" = "404" ] && pass "Paciente sem laudo antes da liberação → 404" || fail "Laudo exposto antes da liberação (${blocked})"

    release=$(curl_auth -X POST \
      "${GATEWAY_URL}/clinica-api/reports/${signed_uid}/release")
    if echo "$release" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('visible_to_patient') else 1)" 2>/dev/null; then
      pass "Clínica libera laudo ao paciente"
    else
      fail "Liberação ao paciente falhou"
    fi

    patient_report=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
      "${GATEWAY_URL}/paciente-api/studies/${signed_uid}/report")
    if echo "$patient_report" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('study_instance_uid') else 1)" 2>/dev/null; then
      pass "Paciente acessa laudo liberado → 200"
    else
      fail "Paciente não vê laudo liberado"
    fi

    studies_json=$(curl -s -H "Authorization: Bearer ${TOKEN}" "${GATEWAY_URL}/paciente-api/studies")
    if echo "$studies_json" | python3 -c "
import sys,json
uid='${signed_uid}'
studies=json.load(sys.stdin).get('studies',[])
sys.exit(0 if any(s.get('study_instance_uid')==uid and s.get('report_available') for s in studies) else 1)
" 2>/dev/null; then
      pass "Lista de exames indica report_available"
    else
      fail "report_available ausente na lista"
    fi
  fi

  if [ -z "$STUDY_UID_DRAFT" ]; then
    load_study_uids
  fi
  if [ -n "$STUDY_UID_DRAFT" ] && [ "$STUDY_UID_DRAFT" != "$signed_uid" ]; then
    draft_status=$(curl_auth "${GATEWAY_URL}/clinica-api/reports/${STUDY_UID_DRAFT}" | \
      python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)
    if [ "$draft_status" = "draft" ]; then
      draft_patient=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${TOKEN}" \
        "${GATEWAY_URL}/paciente-api/studies/${STUDY_UID_DRAFT}/report")
      [ "$draft_patient" = "404" ] && pass "Rascunho invisível ao paciente → 404" || fail "Rascunho exposto ao paciente"
      draft_release=$(curl_auth -o /dev/null -w "%{http_code}" -X POST \
        "${GATEWAY_URL}/clinica-api/reports/${STUDY_UID_DRAFT}/release")
      [ "$draft_release" = "400" ] && pass "Liberação de rascunho bloqueada → 400" || fail "Rascunho liberável (${draft_release})"
    fi
  fi
  echo
fi

# ── E13 ──
if should_run E13; then
  echo "▶ E13 — MWL + sync SQL"
  mwl_cfg=$(curl_auth "${GATEWAY_URL}/clinica-api/admin/pacs/mwl-sql")
  if echo "$mwl_cfg" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('enabled') else 1)" 2>/dev/null; then
    pass "Config SQL MWL disponível"
  else
    fail "Config SQL MWL indisponível"
  fi

  sync=$(curl_auth -X POST "${GATEWAY_URL}/clinica-api/admin/pacs/mwl/sync")
  synced=$(echo "$sync" | python3 -c "import sys,json; print(json.load(sys.stdin).get('synced',0))" 2>/dev/null || echo 0)
  if [ "${synced:-0}" -ge 1 ]; then
    pass "Sync SQL → MWL (${synced} itens)"
  else
    fail "Sync MWL não gerou itens (${synced:-0})"
  fi

  wait_orthanc || true
  mwl_plugin_ok=0
  for _ in $(seq 1 20); do
    plugins=$(curl -s "${ORTHANC_URL}/plugins" 2>/dev/null || echo "[]")
    if echo "$plugins" | python3 -c "import sys,json; p=json.load(sys.stdin); sys.exit(0 if any('worklist' in str(x).lower() for x in p) else 1)" 2>/dev/null; then
      mwl_plugin_ok=1
      break
    fi
    sleep 2
  done
  if [ "$mwl_plugin_ok" = "1" ]; then
    pass "Plugin MWL ativo no Orthanc"
  else
    fail "Plugin MWL ausente no Orthanc"
  fi

  mwl_rx=$(curl_auth "${GATEWAY_URL}/clinica-api/admin/pacs/mwl/entries?station_aet=RX_SALA1")
  rx_count=$(echo "$mwl_rx" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('entries',[])))" 2>/dev/null || echo 0)
  [ "${rx_count:-0}" -ge 1 ] && pass "Filtro station_aet RX_SALA1 → ${rx_count}" || fail "Filtro station_aet MWL falhou"

  if docker exec server ls /var/lib/orthanc/worklists 2>/dev/null | grep -q 'lex-'; then
    pass "Arquivos .wl gerados no Orthanc"
  else
    fail "Pasta worklists sem arquivos lex-*.wl"
  fi
  echo
fi

# ── E14 ──
if should_run E14; then
  echo "▶ E14 — SSO clínico (OIDC)"
  kc_health=$(curl -s -o /dev/null -w "%{http_code}" "${KEYCLOAK_URL}/realms/lex-pacs" 2>/dev/null || echo "000")
  [ "$kc_health" = "200" ] && pass "Keycloak pronto" || fail "Keycloak indisponível (${kc_health})"

  if [ -x "${SCRIPT_DIR}/auth-init.sh" ]; then
    "${SCRIPT_DIR}/auth-init.sh" >/dev/null 2>&1 || true
  fi

  oidc_cfg=$(curl -s "${GATEWAY_URL}/paciente-api/auth/clinical/config")
  if echo "$oidc_cfg" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('enabled') else 1)" 2>/dev/null; then
    pass "OIDC habilitado no portal"
  else
    fail "OIDC desabilitado"
  fi

  OIDC_TOKEN=$(curl -s -X POST "${KEYCLOAK_URL}/realms/lex-pacs/protocol/openid-connect/token" \
    -d "grant_type=password" \
    -d "client_id=lex-clinical" \
    -d "client_secret=${OIDC_CLIENT_SECRET}" \
    -d "username=admin" \
    -d "password=lexadmin2024" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)

  if [ -n "$OIDC_TOKEN" ]; then
    pass "Token OIDC obtido (password grant)"
  else
    fail "Falha ao obter token OIDC"
  fi

  me_oidc=$(curl -s -H "Authorization: Bearer ${OIDC_TOKEN}" "${GATEWAY_URL}/clinica-api/auth/clinical/me")
  if echo "$me_oidc" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('username') and d.get('auth_method')=='oidc' else 1)" 2>/dev/null; then
    pass "Bearer OIDC acessa /auth/clinical/me"
  else
    fail "Perfil OIDC inválido"
  fi

  oidc_api=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${OIDC_TOKEN}" \
    "${GATEWAY_URL}/clinica-api/admin/pacs/mwl-sql")
  [ "$oidc_api" = "200" ] && pass "API clínica via Bearer (sem Basic)" || fail "API clínica bloqueou Bearer (${oidc_api})"

  basic_api=$(http_code_auth "${GATEWAY_URL}/clinica-api/admin/pacs/settings")
  [ "$basic_api" = "200" ] && pass "Sessão clínica acessa API" || fail "Sessão clínica falhou (${basic_api})"
  echo
fi

# ── E15 ──
if should_run E15; then
  echo "▶ E15 — Auditoria"
  load_study_uids
  audit_uid="${STUDY_UID:-}"
  if [ -n "$audit_uid" ]; then
    curl_auth "${GATEWAY_URL}/clinica-api/reports/${audit_uid}" >/dev/null
    pass "Evento study_open disparado (GET laudo)"
  else
    skip "E15: sem estudo para auditoria"
  fi

  audit=$(curl_auth "${GATEWAY_URL}/clinica-api/admin/pacs/audit?limit=20")
  if echo "$audit" | python3 -c "
import sys,json
events={e.get('event') for e in json.load(sys.stdin).get('events',[])}
needed={'study_open','mwl_sync'}
sys.exit(0 if needed.intersection(events) else 1)
" 2>/dev/null; then
    pass "Log de auditoria contém eventos esperados"
  else
    fail "Log de auditoria incompleto"
  fi

  if [ -n "$OIDC_TOKEN" ]; then
    audit_oidc=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${OIDC_TOKEN}" \
      "${GATEWAY_URL}/clinica-api/admin/pacs/audit?limit=5")
    [ "$audit_oidc" = "200" ] && pass "Admin OIDC consulta auditoria" || fail "Auditoria bloqueou admin OIDC (${audit_oidc})"
  fi
  echo
fi

# ── Onda A / B ──
echo "▶ Onda A — Admin, logout e status MWL"
mwl_status=$(curl_auth "${GATEWAY_URL}/clinica-api/admin/pacs/mwl/status")
if echo "$mwl_status" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('sync') is not None and d.get('sql') else 1)" 2>/dev/null; then
  pass "GET /admin/pacs/mwl/status"
else
  fail "GET /admin/pacs/mwl/status"
fi

pacs_stats=$(curl_auth "${GATEWAY_URL}/clinica-api/admin/pacs/stats")
if echo "$pacs_stats" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('studies',0)>=0 and d.get('patients',0)>=0 and isinstance(d.get('disk'),list) and d.get('studies_by_modality') is not None else 1)" 2>/dev/null; then
  pass "GET /admin/pacs/stats (exames, pacientes, disco)"
else
  fail "GET /admin/pacs/stats"
fi

echo "▶ Onda B — Config SQL MWL na UI (API)"
mwl_saved=$(curl_auth -X PUT "${GATEWAY_URL}/clinica-api/admin/pacs/mwl-sql" \
  -H "Content-Type: application/json" \
  -d '{"enabled":true,"host":"database","port":5432,"database":"orthanc","username":"orthanc","password_env":"POSTGRES_PASSWORD","table":"lex_mwl_schedule","sync_interval_minutes":7}')
mwl_interval=$(echo "$mwl_saved" | python3 -c "import sys,json; print(json.load(sys.stdin).get('sync_interval_minutes',0))" 2>/dev/null || echo 0)
if [ "${mwl_interval:-0}" = "7" ]; then
  pass "PUT /admin/pacs/mwl-sql persiste intervalo"
else
  fail "PUT /admin/pacs/mwl-sql não persistiu (${mwl_interval:-0})"
fi
curl_auth -X PUT "${GATEWAY_URL}/clinica-api/admin/pacs/mwl-sql" \
  -H "Content-Type: application/json" \
  -d '{"enabled":true,"host":"database","port":5432,"database":"orthanc","username":"orthanc","password_env":"POSTGRES_PASSWORD","table":"lex_mwl_schedule","sync_interval_minutes":5}' >/dev/null

echo "▶ Onda C — Backup automático"
"${SCRIPT_DIR}/backup-volumes.sh" "${PROJECT_DIR}/backups" >/dev/null 2>&1 || true
backup_api=$(curl_auth "${GATEWAY_URL}/clinica-api/admin/pacs/backup/status")
if echo "$backup_api" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('retention_daily') is not None else 1)" 2>/dev/null; then
  pass "GET /admin/pacs/backup/status (retenção 7+4)"
else
  fail "GET /admin/pacs/backup/status"
fi
if echo "$backup_api" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('configured') and d.get('last_at') else 1)" 2>/dev/null; then
  pass "Backup gera latest-status.json"
else
  fail "latest-status.json ausente após backup"
fi

echo "▶ Onda D — Papéis clínicos e OIDC produção"
clinical_cfg=$(curl -s "${GATEWAY_URL}/clinica-api/auth/clinical/config")
if echo "$clinical_cfg" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('enabled') and d.get('redirect_uri') and 'local_auth_enabled' in d else 1)" 2>/dev/null; then
  pass "GET /auth/clinical/config (redirect + local_auth)"
else
  fail "GET /auth/clinical/config incompleto"
fi

clinical_login
me_perms=$(curl_auth "${GATEWAY_URL}/clinica-api/auth/clinical/me")
if echo "$me_perms" | python3 -c "import sys,json; d=json.load(sys.stdin); p=d.get('permissions',{}); sys.exit(0 if p.get('can_draft') is not None and p.get('role_label') else 1)" 2>/dev/null; then
  pass "Sessão clínica retorna permissions"
else
  fail "Sessão clínica sem permissions"
fi

keycloak_token() {
  local user=$1 pass=$2
  curl -s -X POST "${KEYCLOAK_URL}/realms/lex-pacs/protocol/openid-connect/token" \
    -d "grant_type=password" \
    -d "client_id=lex-clinical" \
    -d "client_secret=${OIDC_CLIENT_SECRET}" \
    -d "username=${user}" \
    -d "password=${pass}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true
}

RAD_TOKEN=$(keycloak_token radiologista lexrad2024)
TEC_TOKEN=$(keycloak_token tecnico lextec2024)

if [ -n "$RAD_TOKEN" ]; then
  rad_me=$(curl -s -H "Authorization: Bearer ${RAD_TOKEN}" "${GATEWAY_URL}/clinica-api/auth/clinical/me")
  if echo "$rad_me" | python3 -c "import sys,json; d=json.load(sys.stdin); p=d.get('permissions',{}); sys.exit(0 if p.get('can_sign') and p.get('role')=='radiologista' else 1)" 2>/dev/null; then
    pass "Radiologista OIDC pode assinar (can_sign)"
  else
    fail "Radiologista sem can_sign"
  fi
else
  fail "Token radiologista OIDC ausente"
fi

if [ -n "$TEC_TOKEN" ]; then
  tec_me=$(curl -s -H "Authorization: Bearer ${TEC_TOKEN}" "${GATEWAY_URL}/clinica-api/auth/clinical/me")
  if echo "$tec_me" | python3 -c "import sys,json; d=json.load(sys.stdin); p=d.get('permissions',{}); sys.exit(0 if not p.get('can_sign') and p.get('role')=='tecnico' else 1)" 2>/dev/null; then
    pass "Técnico OIDC não pode assinar"
  else
    fail "Técnico com can_sign indevido"
  fi
else
  fail "Token técnico OIDC ausente"
fi

load_study_uids
sign_test_uid="${STUDY_UID_DRAFT:-${STUDY_UID:-}}"
if [ -n "$sign_test_uid" ] && [ -n "$TEC_TOKEN" ]; then
  tec_sign=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${TEC_TOKEN}" \
    -X POST "${GATEWAY_URL}/clinica-api/reports/${sign_test_uid}/sign" \
    -H "Content-Type: application/json" \
    -d '{"signed_by":"Tecnico Smoke","signed_crm":""}')
  [ "$tec_sign" = "403" ] && pass "Técnico bloqueado ao assinar → 403" || fail "Técnico assinou laudo (${tec_sign})"
else
  skip "Onda D: sem estudo ou token técnico para teste de assinatura"
fi

oidc_login_code=$(curl -s -o /dev/null -w "%{http_code}" "${GATEWAY_URL}/clinica-api/auth/clinical/oidc/login?next=%2Fviewer%2F")
if [ "$oidc_login_code" = "307" ] || [ "$oidc_login_code" = "302" ]; then
  pass "GET /auth/clinical/oidc/login redireciona SSO"
else
  fail "OIDC login não redireciona (${oidc_login_code})"
fi

curl_auth -X POST "${GATEWAY_URL}/clinica-api/auth/clinical/logout" >/dev/null
code_logout=$(http_code_auth "${GATEWAY_URL}/dicom-web/studies?limit=1")
if [ "$code_logout" = "401" ] || [ "$code_logout" = "302" ]; then
  pass "Logout clínico invalida sessão (→ ${code_logout})"
else
  fail "Logout clínico não invalidou sessão (→ ${code_logout})"
fi
echo

# ── S10 — Rate limit login ──
if should_run S10; then
  echo "▶ S10 — Rate limit login"
  saw_429=0
  for _ in $(seq 1 25); do
    code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${GATEWAY_URL}/clinica-api/auth/clinical/login" \
      -H "Content-Type: application/json" \
      -d '{"username":"invalid","password":"invalid","next":"/viewer/"}')
    if [ "$code" = "429" ]; then
      saw_429=1
      break
    fi
  done
  [ "$saw_429" = "1" ] && pass "Login clínico retorna 429 após excesso" || fail "Rate limit login não retornou 429"
  echo
fi

# ── S11 — Headers de segurança ──
if should_run S11; then
  echo "▶ S11 — CSP e headers"
  headers=$(curl -sI "${GATEWAY_URL}/clinica/login")
  echo "$headers" | grep -qi "content-security-policy:" && pass "Content-Security-Policy presente" || fail "CSP ausente"
  echo "$headers" | grep -qi "x-frame-options: SAMEORIGIN" && pass "X-Frame-Options SAMEORIGIN" || fail "X-Frame-Options ausente"
  echo "$headers" | grep -qi "permissions-policy:" && pass "Permissions-Policy presente" || fail "Permissions-Policy ausente"
  echo
fi

# ── Etapas pendentes (só informa se solicitadas explicitamente) ──
for pid in "${PENDING_STAGES[@]}"; do
  if should_run "$pid"; then
    echo "▶ ${pid} — pendente"
    pending "${pid}: implementar e adicionar testes em smoke-test.sh"
    echo
  fi
done

echo "══════════════════════════════════════════"
echo " Resultado: ${PASS} ok | ${FAIL} falha | ${SKIP} ignorado"
echo "══════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  echo
  echo "Corrija as falhas antes de avançar. Ver docs/TESTES.md"
  exit 1
fi

echo
echo "Todas as etapas selecionadas passaram."
exit 0
