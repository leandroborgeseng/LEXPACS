"""Paginação no servidor + busca sem acento (POST /clinica-api/worklist/studies) via gateway real,
contra Orthanc LOCAL descartável com estudos SINTÉTICOS. Roda só via scripts/it-busca-curinga.sh."""
import os
import time
from pathlib import Path

import httpx
import pytest

GW = os.environ.get("LEX_IT_GATEWAY")
pytestmark = pytest.mark.skipif(not GW, reason="integração: rode scripts/it-busca-curinga.sh")
N = int(os.environ.get("LEX_IT_N", "0"))
API = "/clinica-api/worklist/studies"


@pytest.fixture(scope="module")
def s():
    c = httpx.Client(base_url=GW, timeout=120)
    for pw in ("Admin-Nova-IT-2026", "Admin-Inicial-IT1"):
        r = c.post("/clinica-api/auth/clinical/login", json={"username": "admin", "password": pw})
        if r.status_code == 200:
            break
    assert r.status_code == 200, r.text
    if r.json().get("must_change_password"):
        c.post("/clinica-api/auth/clinical/change-password",
               json={"current_password": "Admin-Inicial-IT1", "new_password": "Admin-Nova-IT-2026"})
    yield c


def post(s, **body):
    t = time.perf_counter()
    r = s.post(API, json=body)
    dt = time.perf_counter() - t
    assert r.status_code == 200, (r.status_code, r.text[:300])
    out = r.json()
    print(f"\n{body} -> total={out['total']} n={len(out['studies'])} hasMore={out['hasMore']} {dt:.3f}s")
    return out


def ids(res):
    return [x.get("00100020", {}).get("Value", [""])[0] for x in res["studies"]]


def test_paginacao_alem_dos_101_sem_repetir(s):
    pages = [post(s, limit=50, offset=o) for o in (0, 50, 100, 150)]
    assert pages[0]["total"] >= N > 150
    all_ids = [i for p in pages for i in ids(p)]
    assert len(all_ids) == 200 and len(set(all_ids)) == 200


@pytest.mark.parametrize("typed", ["jose conceicao", "JOSÉ CONCEIÇÃO", "conceicao jose", "zzteste"])
def test_nome_sem_acento_acha_2023(s, typed):
    res = post(s, patientName=typed)
    assert "SINT-ZZ-2023" in ids(res), typed


def test_nome_gravado_com_acento_avila(s):
    assert "SINT-ALVO-ACENTO" in ids(post(s, patientName="joao avila"))


def test_busca_por_data_2023(s):
    res = post(s, startDate="20230505", endDate="20230505")
    assert "SINT-ZZ-2023" in ids(res)
    assert all(x["00080020"]["Value"][0] == "20230505" for x in res["studies"])


def test_nome_exibido_sem_virgula(s):
    res = post(s, patientId="SINT-ZZ-2023")
    assert ids(res) == ["SINT-ZZ-2023"]


def test_lp9_zzteste_fora_dos_logs(s):
    post(s, patientName="zzteste conceicao")
    time.sleep(0.5)
    it = Path(os.environ["LEX_IT_ACCESS_LOG"]).parent.parent
    logs = [p for p in it.rglob("*.log")]
    assert logs
    for p in logs:
        text = p.read_text(encoding="utf-8", errors="replace")
        assert "ZZTESTE" not in text.upper(), p.name
        assert "SINT-ZZ-2023" not in text, p.name
