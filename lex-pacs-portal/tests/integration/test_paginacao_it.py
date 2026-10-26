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
    assert pages[0]["total"] is None or pages[0]["total"] >= N > 150
    assert all(p["hasMore"] for p in pages[:3])
    all_ids = [i for p in pages for i in ids(p)]
    assert len(all_ids) == 200 and len(set(all_ids)) == 200


@pytest.mark.parametrize("typed", ["jose conceicao", "JOSÉ CONCEIÇÃO", "conceicao jose", "zzteste jose conceicao"])
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


def test_lpt_c_nome_comum_alem_da_pagina_1(s):
    p1 = post(s, patientName="oliveira", limit=10, offset=0)
    p2 = post(s, patientName="oliveira", limit=10, offset=10)
    assert p1["total"] and p1["total"] > 20 and p1["hasMore"]
    assert len(p2["studies"]) == 10 and not set(ids(p1)) & set(ids(p2))


def test_tempos_indice(s):
    """Tempos (3 medições cada) via gateway real; o índice já está carregado nos testes acima."""
    total = post(s, limit=50)["total"]
    last = (total - 1) // 50 * 50
    casos = {"nome 'ana'": dict(patientName="ana"), "nome 'jose'": dict(patientName="jose"),
             "nome 'maria'": dict(patientName="maria"), "primeira página": dict(offset=0),
             f"última página (offset {last})": dict(offset=last)}
    print("\n== Tempos do índice (s), POST /clinica-api/worklist/studies ==")
    for label, body in casos.items():
        runs = []
        for _ in range(3):
            t = time.perf_counter()
            r = s.post(API, json={"limit": 50, **body})
            runs.append(time.perf_counter() - t)
            assert r.status_code == 200
        out = r.json()
        print(f"{label}: total={out['total']} n={len(out['studies'])} " + ", ".join(f"{x:.3f}" for x in runs))
        assert out["studies"], label
        assert max(runs) < 3.0, label


def test_incremental_changes_orthanc_real(s):
    """Estudo novo no Orthanc LOCAL descartável aparece na busca pelo /changes (sem recarga)."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from gerar_sinteticos import dataset

    url = os.environ["LEX_IT_ORTHANC"]
    assert "127.0.0.1" in url
    auth = tuple(os.environ["LEX_IT_ORTHANC_AUTH"].split(":", 1))
    httpx.post(f"{url}/instances", content=dataset(999999, "ZZTESTE^INCREMENTAL JOÃO", "SINT-INCR", "20261026", "CT"),
               auth=auth).raise_for_status()
    assert ids(post(s, patientName="incremental joao")) == ["SINT-INCR"]
