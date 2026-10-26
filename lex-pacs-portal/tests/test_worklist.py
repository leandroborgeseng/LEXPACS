"""Lista paginada no servidor e busca sem acento (POST /api/worklist/studies) — dados SINTÉTICOS.

O Orthanc falso imita o real (1.12.x, conferido em Orthanc local descartável): compara sem
diferenciar maiúsculas, mas NÃO ignora acento, e "*" é curinga.
"""
import asyncio
import fnmatch
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app import worklist
from app.worklist import (
    WorklistQuery,
    name_matcher,
    normalize_name,
    orthanc_name_pattern,
)

NOMES = [
    ("CONCEIÇÃO^JOSÉ", "SINT-ACENTO", "20190610"),
    ("CONCEICAO^JOSE", "SINT-SEM", "20180315"),
    ("ÁVILA^JOÃO", "SINT-AVILA", "20200101"),
    ("SILVA^MARIA", "SINT-SILVA", "20261020"),
]
STUDIES = [
    {"uid": f"1.2.826.0.1.3680043.8.498.{i}", "name": n, "pid": p, "date": d, "mod": "CT" if i % 2 else "MR"}
    for i, (n, p, d) in enumerate(NOMES)
] + [
    {"uid": f"1.2.826.0.1.3680043.8.498.9{i:04d}", "name": f"SANTOS^ANA {i:05d}", "pid": f"SINT-{i:06d}",
     "date": f"2025{(i % 12) + 1:02d}{(i % 28) + 1:02d}", "mod": "CR"}
    for i in range(120)
]


def _match(pattern: str, value: str) -> bool:
    return fnmatch.fnmatchcase(value.upper(), pattern.upper().replace("[", "[[]"))


def _dicom(s):
    return {
        "0020000D": {"vr": "UI", "Value": [s["uid"]]},
        "00100010": {"vr": "PN", "Value": [{"Alphabetic": s["name"]}]},
        "00100020": {"vr": "LO", "Value": [s["pid"]]},
        "00080020": {"vr": "DA", "Value": [s["date"]]},
        "00080061": {"vr": "CS", "Value": [s["mod"]]},
    }


def _filter(studies, q):
    out = []
    for s in studies:
        if "PatientName" in q and not _match(q["PatientName"], s["name"]):
            continue
        if "PatientID" in q and q["PatientID"] != s["pid"]:
            continue
        if "ModalitiesInStudy" in q and s["mod"] not in q["ModalitiesInStudy"].split("\\"):
            continue
        if "StudyDate" in q:
            a, _, b = q["StudyDate"].partition("-")
            if (a and s["date"] < a) or (b and s["date"] > b):
                continue
        out.append(s)
    return out


class FakeOrthanc:
    def __init__(self):
        self.calls = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        path = request.url.path
        if request.method == "GET" and path == "/dicom-web/studies":
            qs = {k: v[0] for k, v in parse_qs(urlparse(str(request.url)).query).items()}
            if "StudyInstanceUID" in qs:
                uids = set(qs["StudyInstanceUID"].split(","))
                rows = [s for s in STUDIES if s["uid"] in uids]
            else:
                rows = _filter(STUDIES, qs)
                off, lim = int(qs.get("offset", 0)), int(qs.get("limit", 101))
                rows = rows[off: off + lim]
            return httpx.Response(200, json=[_dicom(s) for s in rows])
        body = json.loads(request.content or b"{}")
        if request.method == "POST" and path == "/tools/find":
            rows = _filter(STUDIES, body["Query"])[: body.get("Limit") or None]
            return httpx.Response(200, json=[
                {"MainDicomTags": {"StudyInstanceUID": s["uid"], "StudyDate": s["date"]},
                 "PatientMainDicomTags": {"PatientName": s["name"]}} for s in rows])
        if request.method == "POST" and path == "/tools/count-resources":
            return httpx.Response(200, json={"Count": len(_filter(STUDIES, body["Query"]))})
        return httpx.Response(404)


@pytest.fixture
def orthanc(monkeypatch):
    fake = FakeOrthanc()
    real = httpx.AsyncClient

    def factory(*a, **kw):
        kw["transport"] = httpx.MockTransport(fake)
        return real(*a, **kw)

    monkeypatch.setattr(worklist.httpx, "AsyncClient", factory)
    monkeypatch.setattr(worklist.settings, "orthanc_url", "http://orthanc-sintetico.invalid:8042")
    return fake


def _run(**kw):
    return asyncio.run(worklist.worklist_studies(WorklistQuery(**kw)))


def _names(r):
    return [s["00100010"]["Value"][0]["Alphabetic"] for s in r["studies"]]


def test_normalizacao_e_padrao():
    assert normalize_name("  José   Conceição ") == "JOSE CONCEICAO"
    assert normalize_name("SILVA^MARIA*?") == "SILVA MARIA"
    assert orthanc_name_pattern("jose conceicao") == "*J*S*"
    assert orthanc_name_pattern("conceição") == "*N*"
    assert orthanc_name_pattern("José") == "*J*S*"
    assert orthanc_name_pattern("li") == "L*"
    assert orthanc_name_pattern("") is None
    m = name_matcher("jose conceicao")
    assert m("CONCEIÇÃO^JOSÉ") and m("CONCEICAO^JOSE") and not m("CONCEIÇÃO^MARIA")


@pytest.mark.parametrize("typed", ["jose conceicao", "JOSÉ CONCEIÇÃO", "conceição", "Conceicao", "CONCEI"])
def test_sem_acento_acha_gravado_com_e_sem_acento(orthanc, typed):
    r = _run(patientName=typed)
    assert set(_names(r)) == {"CONCEIÇÃO^JOSÉ", "CONCEICAO^JOSE"}
    assert r["total"] == 2 and r["hasMore"] is False


def test_vice_versa_digitado_com_acento_acha_gravado_sem(orthanc):
    assert "CONCEICAO^JOSE" in _names(_run(patientName="José Conceição"))
    assert _names(_run(patientName="joao avila")) == ["ÁVILA^JOÃO"]
    assert _names(_run(patientName="JOÃO ÁVILA")) == ["ÁVILA^JOÃO"]


def test_nome_ordena_mais_recente_primeiro(orthanc):
    r = _run(patientName="conceicao")
    assert _names(r) == ["CONCEIÇÃO^JOSÉ", "CONCEICAO^JOSE"]  # 2019 antes de 2018


def test_paginacao_sem_filtro_tem_total_e_lotes_distintos(orthanc):
    p1 = _run(limit=50, offset=0)
    p2 = _run(limit=50, offset=50)
    p3 = _run(limit=50, offset=100)
    assert p1["total"] == len(STUDIES) == 124
    assert len(p1["studies"]) == 50 and len(p2["studies"]) == 50 and len(p3["studies"]) == 24
    uids = [s["0020000D"]["Value"][0] for p in (p1, p2, p3) for s in p["studies"]]
    assert len(uids) == len(set(uids)) == 124  # nenhum exame repetido entre páginas (LP3)
    assert p1["hasMore"] and p2["hasMore"] and not p3["hasMore"]


def test_paginacao_com_nome(orthanc):
    r1 = _run(patientName="santos ana", limit=50, offset=0)
    r3 = _run(patientName="santos ana", limit=50, offset=100)
    assert r1["total"] == 120 and len(r1["studies"]) == 50 and len(r3["studies"]) == 20
    assert not set(_names(r1)) & set(_names(r3))


def test_sem_count_resources_total_desconhecido(orthanc, monkeypatch):
    async def no_count(*_a, **_k):
        return None
    monkeypatch.setattr(worklist, "_count", no_count)
    r = _run(limit=50, offset=50)
    assert r["total"] is None and r["hasMore"] is True and len(r["studies"]) == 50


def test_filtros_modalidade_data_id(orthanc):
    assert _names(_run(patientId="SINT-SILVA")) == ["SILVA^MARIA"]
    r = _run(startDate="20260101", endDate="20261231")
    assert _names(r) == ["SILVA^MARIA"] and r["total"] == 1
    assert all(s["00080061"]["Value"] == ["CR"] for s in (_run(modalitiesInStudy=["CR"]))["studies"])


def test_limite_de_candidatos_total_desconhecido(orthanc, monkeypatch):
    monkeypatch.setattr(worklist, "MAX_CANDIDATOS", 10)
    r = _run(patientName="santos", limit=5)
    assert r["truncated"] is True and r["total"] is None and r["hasMore"] is True


def test_so_leitura_no_orthanc(orthanc):
    _run(patientName="conceicao")
    _run()
    for method, path in orthanc.calls:
        assert (method, path) in {("GET", "/dicom-web/studies"), ("POST", "/tools/find"),
                                  ("POST", "/tools/count-resources")}, (method, path)


def test_validacao():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _run(startDate="2026-01-01")
    with pytest.raises(HTTPException):
        _run(modalitiesInStudy=["CT;DROP"])


def test_exige_sessao_clinica(client):
    r = client.post("/api/worklist/studies", json={"patientName": "conceicao"})
    assert r.status_code == 401
