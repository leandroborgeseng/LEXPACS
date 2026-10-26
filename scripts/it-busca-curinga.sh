#!/usr/bin/env bash
# Integração LP4 (busca com curinga) contra um Orthanc LOCAL DESCARTÁVEL com estudos sintéticos.
# Nunca aponte para o Orthanc de produção. Requer: Orthanc + plugin DicomWeb, nginx, envsubst,
# node e um Python com as dependências do portal (pytest, httpx, pydicom, uvicorn).
#   N_STUDIES=1500 scripts/it-busca-curinga.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IT="${IT_DIR:-$(mktemp -d /tmp/lex-it-XXXX)}"
N="${N_STUDIES:-1500}"
ORTHANC_BIN="${ORTHANC_BIN:-$(command -v Orthanc || echo /usr/sbin/Orthanc)}"
NGINX_BIN="${NGINX_BIN:-$(command -v nginx || echo /usr/sbin/nginx)}"
PLUGIN="${ORTHANC_DICOMWEB_PLUGIN:-$(ls /usr/share/orthanc/plugins/libOrthancDicomWeb.so 2>/dev/null || true)}"
OPW="it-$(head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n')"
PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done; [ -f "$IT/nginx/nginx.pid" ] && kill "$(cat "$IT/nginx/nginx.pid")" 2>/dev/null || true; }
trap cleanup EXIT
mkdir -p "$IT/db" "$IT/nginx/conf.d" "$IT/nginx/tmp" "$IT/data"
cat > "$IT/orthanc.json" <<JSON
{ "Name": "ORTHANC-IT-DESCARTAVEL", "StorageDirectory": "$IT/db", "IndexDirectory": "$IT/db",
  "HttpPort": 18142, "DicomServerEnabled": false, "RemoteAccessAllowed": false,
  "AuthenticationEnabled": true, "RegisteredUsers": { "leitor": "$OPW" },
  "Plugins": ["$PLUGIN"], "DicomWeb": { "Enable": true, "Root": "/dicom-web/", "QidoCaseSensitive": false } }
JSON
"$ORTHANC_BIN" "$IT/orthanc.json" > "$IT/orthanc.log" 2>&1 & PIDS+=($!)
for i in $(seq 1 30); do curl -fs -u "leitor:$OPW" http://127.0.0.1:18142/system >/dev/null && break; sleep 1; done
echo "Orthanc: $(curl -fs -u "leitor:$OPW" http://127.0.0.1:18142/system | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["Version"], "DicomWeb" , "ok")')"

T0=$(date +%s)
ORTHANC_USERNAME=leitor ORTHANC_PASSWORD="$OPW" python3 "$ROOT/lex-pacs-portal/tests/integration/gerar_sinteticos.py" --url http://127.0.0.1:18142 --n "$N"
echo "Carga de $N estudos sintéticos: $(( $(date +%s) - T0 )) s"

cd "$ROOT/lex-pacs-portal"
ORTHANC_URL=http://127.0.0.1:18142 ORTHANC_USERNAME=leitor ORTHANC_PASSWORD="$OPW" ORTHANC_EXTERNAL_READONLY=true \
JWT_SECRET="it-$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')" LEX_ADMIN_USER=admin LEX_ADMIN_PASSWORD=Admin-Inicial-IT1 \
LOCAL_USERS_DB_PATH="$IT/data/users.db" AUDIT_DATA_PATH="$IT/data/audit" REPORTS_DATA_PATH="$IT/data/reports" \
  python3 -m uvicorn app.main:app --host 127.0.0.1 --port 18180 > "$IT/portal.log" 2>&1 & PIDS+=($!)
cd "$ROOT"

export LEX_ORTHANC_URL=http://127.0.0.1:18142 LEX_ORTHANC_USERNAME=leitor LEX_ORTHANC_PASSWORD="$OPW"
. "$ROOT/ohif-viewer/nginx/15-lex-orthanc.envsh"
envsubst '${LEX_ORTHANC_URL} ${LEX_ORTHANC_AUTH_HEADER}' < "$ROOT/ohif-viewer/nginx/gateway.conf.template" \
  | sed -e 's/listen 80;/listen 127.0.0.1:18100;/' -e '/resolver 127.0.0.11/d' \
        -e 's/set $lex_upstream_portal portal;/set $lex_upstream_portal 127.0.0.1;/' \
        -e 's/\$lex_upstream_portal:8080/$lex_upstream_portal:18180/g' -e 's/\$lex_upstream_viewer:80/127.0.0.1:18181/g' \
        -e "s#/var/log/nginx/access.log#$IT/nginx/access.log#" > "$IT/nginx/conf.d/default.conf"
cp "$ROOT/ohif-viewer/nginx/00-lex-security.conf" "$IT/nginx/conf.d/"
cat > "$IT/nginx/nginx.conf" <<NG
worker_processes 1; pid $IT/nginx/nginx.pid; error_log $IT/nginx/error.log;
events {}
http { access_log $IT/nginx/access-default.log; client_body_temp_path $IT/nginx/tmp; proxy_temp_path $IT/nginx/tmp;
  fastcgi_temp_path $IT/nginx/tmp; uwsgi_temp_path $IT/nginx/tmp; scgi_temp_path $IT/nginx/tmp;
  include $IT/nginx/conf.d/*.conf; }
NG
"$NGINX_BIN" -c "$IT/nginx/nginx.conf" -p "$IT/nginx"
for i in $(seq 1 30); do curl -fs http://127.0.0.1:18180/api/health >/dev/null && break; sleep 1; done

LEX_IT_GATEWAY=http://127.0.0.1:18100 LEX_IT_ACCESS_LOG="$IT/nginx/access.log" LEX_IT_ORTHANC=http://127.0.0.1:18142 \
LEX_IT_ORTHANC_AUTH="leitor:$OPW" LEX_IT_N="$N" LEX_IT_ROOT="$ROOT" LEX_IT_INDEX_PATH="$IT/data/worklist_index.db" \
  python3 -m pytest -q -s "$ROOT/lex-pacs-portal/tests/integration" -p no:cacheprovider
