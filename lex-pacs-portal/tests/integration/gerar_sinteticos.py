"""Gera N estudos DICOM SINTÉTICOS e envia a um Orthanc descartável (localhost/127.0.0.1/server).

O gerador fica em app/homolog_seed.py (também usado pelo serviço seed-homolog do compose).
Credenciais: --user/--password ou ORTHANC_USERNAME/ORTHANC_PASSWORD.
"""
import argparse
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.homolog_seed import checar_host, dataset, enviar, plano  # noqa: E402,F401


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--user", default=os.environ.get("ORTHANC_USERNAME", ""))
    ap.add_argument("--password", default=os.environ.get("ORTHANC_PASSWORD", ""))
    ap.add_argument("--n", type=int, default=1500)
    ap.add_argument("--maria", type=int, default=0, help="estudos MARIA (0 = distribuição uniforme)")
    a = ap.parse_args()
    url = checar_host(a.url)
    with httpx.Client(auth=(a.user, a.password) if a.user else None, timeout=60) as client:
        enviar(client, url, plano(a.n, a.maria))


if __name__ == "__main__":
    main()
