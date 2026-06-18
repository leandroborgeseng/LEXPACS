#!/bin/sh
# Lista PatientID (tag DICOM 0010,0020) dos pacientes no Orthanc.
# Uso: ./scripts/list-patient-ids.sh [ORTHANC_URL]
BASE="${1:-http://localhost:8042}"

IDS=$(curl -sf "$BASE/tools/find" -H "Content-Type: application/json" \
  -d '{"Level":"Patient","Query":{}}') || { echo "Erro ao conectar em $BASE"; exit 1; }

echo "PatientID | Nome | Nascimento"
echo "----------|------|------------"

for id in $(echo "$IDS" | python3 -c "import sys,json; print(' '.join(json.load(sys.stdin)))"); do
  curl -sf "$BASE/patients/$id" | python3 -c "
import sys, json
p = json.load(sys.stdin)
t = p.get('MainDicomTags', {})
pid = t.get('PatientID', '—')
name = t.get('PatientName', '—').replace('^', ' ')
birth = t.get('PatientBirthDate', '—')
if birth and len(birth) == 8:
    birth = f\"{birth[6:8]}/{birth[4:6]}/{birth[0:4]}\"
print(f'{pid} | {name} | {birth}')
"
done
