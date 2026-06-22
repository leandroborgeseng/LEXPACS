#!/usr/bin/env bash
# Envia ORM^O01 de teste via MLLP para o portal (E18).
set -euo pipefail

HOST="${HL7_HOST:-127.0.0.1}"
PORT="${HL7_PORT:-2575}"
ACCESSION="${HL7_ACCESSION:-LEXHL7$(date +%H%M%S)}"
STAMP=$(date +%Y%m%d%H%M%S)

MSG=$(cat <<EOF
MSH|^~\&|RIS|CLINICA|LEXPACS|LEX|${STAMP}||ORM^O01|MSG${STAMP}|P|2.5
PID|1||HL7PAT001^^^CLINIC||TESTE^HL7 ORM||19800101|M
ORC|NW|PL${ACCESSION}|${ACCESSION}|||||||${STAMP}
OBR|1|PL${ACCESSION}|${ACCESSION}|CTCHEST^TC TORAX|||||||||${STAMP}||||||||CT|${STAMP}||||F
EOF
)

python3 <<PY
import socket
host = "${HOST}"
port = int("${PORT}")
msg = """${MSG}""".replace("\n", "\r") + "\r"
frame = b"\x0b" + msg.encode("utf-8") + b"\x1c\x0d"
with socket.create_connection((host, port), timeout=10) as sock:
    sock.sendall(frame)
    resp = sock.recv(65536)
print(resp.decode("utf-8", errors="replace"))
print("Accession enviada: ${ACCESSION}")
PY
