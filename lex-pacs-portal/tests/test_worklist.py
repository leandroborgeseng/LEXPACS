"""Índice da lista de exames + POST /api/worklist/studies — só dados SINTÉTICOS (ZZTESTE).

O Orthanc falso responde só o que o portal usa: QIDO GET (paginado e por UID), /changes e
/studies/{id}. Qualquer outro método/rota falha o teste (só leitura).
"""
import asyncio
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app import worklist, worklist_index
from app.worklist import WorklistQuery
from app.worklist_index import normalize_text, orthanc_study_id


def _mk(i, name, pid, date, mod="CR", time="101500"):
    return {"uid": f"1.2.826.0.1.3680043.8.498.{i}", "name": name, "pid": pid, "date": date,
            "time": time, "mod": mod, "acc": f"ACC-{i:05d}"}


BASE = [
    _mk(1, "ZZTESTE^JOSÉ CONCEIÇÃO", "SINT-ZZ-2023", "20230505", "CT"),
    _mk(2, "ZZTESTE^JOSE CONCEICAO", "SINT-SEM", "20180315", "MR"),
    _mk(3, "ÁVILA^JOÃO ZZTESTE", "SINT-AVILA", "20190610", "MR"),
    _mk(4, "ZZTESTE^MARIA SILVA", "SINT-SILVA", "20261020", "CT"),
] + [_mk(100 + i, f"ZZTESTE^ANA {i:05d}", f"SINT-{i:06d}", f"2025{(i % 12) + 1:02d}{(i % 28) + 1:02d}")
     for i in range(120)]


def _dicom(s):
    return {
        "0020000D": {"vr": "UI", "Value": [s["uid"]]},
        "00100010": {"vr": "PN", "Value": [{"Alphabetic": s["name"]}]},
        "00100020": {"vr": "LO", "Value": [s["pid"]]},
        "00080020": {"vr": "DA", "Value": [s["date"]]},
        "00080030": {"vr": "TM", "Value": [s["time"]]},
        "00080050": {"vr": "SH", "Value": [s["acc"]]},
        "00080061": {"vr": "CS", "Value": [s["mod"]]},
    }


class FakeOrthanc:
    def __init__(self, studies):
        self.studies = list(studies)
        self.changes = []
        self.calls = []
        self.limit_find = None  # simula LimitFindResults do Orthanc (corta cada consulta)
        self.extra_count = 0  # /statistics conta estudos que o QIDO não devolve

    def add(self, s):
        self.studies.append(s)
        self.changes.append({"Seq": len(self.changes) + 1, "ChangeType": "StableStudy",
                             "ResourceType": "Study", "ID": orthanc_study_id(s["pid"], s["uid"])})

    def delete(self, uid):
        s = next(x for x in self.studies if x["uid"] == uid)
        self.studies.remove(s)
        self.changes.append({"Seq": len(self.changes) + 1, "ChangeType": "Deleted",
                             "ResourceType": "Study", "ID": orthanc_study_id(s["pid"], s["uid"])})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        assert request.method == "GET", request.method
        qs = {k: v[0] for k, v in parse_qs(urlparse(str(request.url)).query, keep_blank_values=True).items()}
        path = request.url.path
        if path == "/dicom-web/studies":
            if "StudyInstanceUID" in qs:
                uids = set(qs["StudyInstanceUID"].split(","))
                rows = [s for s in self.studies if s["uid"] in uids]
            else:
                off, lim = int(qs.get("offset", 0)), int(qs.get("limit", 101))
                if self.limit_find:
                    lim = min(lim, self.limit_find)
                rows = self.studies[off: off + lim]
            return httpx.Response(200, json=[_dicom(s) for s in rows])
        if path == "/changes":
            if "last" in qs:
                return httpx.Response(200, json={"Changes": [], "Done": True, "Last": len(self.changes)})
            since, lim = int(qs.get("since", 0)), int(qs.get("limit", 100))
            chunk = [c for c in self.changes if c["Seq"] > since][:lim]
            last = chunk[-1]["Seq"] if chunk else since
            return httpx.Response(200, json={"Changes": chunk, "Done": last >= len(self.changes), "Last": last})
        if path == "/statistics":
            return httpx.Response(200, json={"CountStudies": len(self.studies) + self.extra_count})
        if path.startswith("/studies/"):
            oid = path.rsplit("/", 1)[1]
            for s in self.studies:
                if orthanc_study_id(s["pid"], s["uid"]) == oid:
                    return httpx.Response(200, json={"MainDicomTags": {"StudyInstanceUID": s["uid"]}})
            return httpx.Response(404)
        return httpx.Response(404)


_REAL = httpx.AsyncClient


@pytest.fixture
def raw_orthanc(monkeypatch, tmp_path):
    fake = FakeOrthanc(BASE)

    def factory(*a, **kw):
        kw["transport"] = httpx.MockTransport(fake)
        return _REAL(*a, **kw)

    for mod in (worklist, worklist_index):
        monkeypatch.setattr(mod.httpx, "AsyncClient", factory)
    monkeypatch.setattr(worklist.settings, "orthanc_url", "http://orthanc-sintetico.invalid:8042")
    monkeypatch.setattr(worklist.settings, "worklist_index_path", str(tmp_path / "idx.db"))
    worklist_index._set_state(status="idle", indexed=0, total=None)
    return fake


@pytest.fixture
def orthanc(raw_orthanc):
    """Índice já carregado (o caso comum depois do startup)."""
    asyncio.run(worklist_index._sync_now_for_tests())
    return raw_orthanc


def _run(**kw):
    return asyncio.run(worklist.worklist_studies(WorklistQuery(**kw)))


def _pids(r):
    return [s["00100020"]["Value"][0] for s in r["studies"]]


def test_normalizacao():
    assert normalize_text("  José   Conceição ") == "jose conceicao"
    assert normalize_text("ZZTESTE^MARIA*%_") == "zzteste maria"
    # ID do estudo no Orthanc = SHA-1 de "PatientID|StudyInstanceUID"
    assert orthanc_study_id("A", "1.2") == "-".join(__import__("hashlib").sha1(b"A|1.2").hexdigest()[i:i + 8]
                                                   for i in range(0, 40, 8))


@pytest.mark.parametrize("typed", ["jose conceicao", "JOSÉ CONCEIÇÃO", "conceicao jose", "Conceição"])
def test_sem_acento_qualquer_ordem(orthanc, typed):
    r = _run(patientName=typed)
    assert _pids(r) == ["SINT-ZZ-2023", "SINT-SEM"]  # 2023 antes de 2018
    assert r["total"] == 2 and not r["hasMore"]


def test_vice_versa_e_sem_curinga_relaxado(orthanc):
    assert _pids(_run(patientName="joao avila")) == ["SINT-AVILA"]
    assert _pids(_run(patientName="JOÃO ÁVILA")) == ["SINT-AVILA"]
    # "ana" não vira *N*: só nomes que contêm "ana"
    r = _run(patientName="ana", limit=200)
    assert r["total"] == 120 and all("ANA" in s["00100010"]["Value"][0]["Alphabetic"] for s in r["studies"])


def test_ordem_global_e_paginas_sem_repetir(orthanc):
    datas, uids = [], []
    for off in (0, 50, 100):
        r = _run(limit=50, offset=off)
        assert r["total"] == len(BASE) and r["sortScope"] == "global"
        datas += [s["00080020"]["Value"][0] for s in r["studies"]]
        uids += [s["0020000D"]["Value"][0] for s in r["studies"]]
    assert len(uids) == len(set(uids)) == len(BASE)
    assert datas == sorted(datas, reverse=True)


def test_filtros_data_modalidade_id(orthanc):
    assert _pids(_run(startDate="20230505", endDate="20230505")) == ["SINT-ZZ-2023"]
    assert _pids(_run(patientId="SINT-SILVA")) == ["SINT-SILVA"]
    r = _run(modalitiesInStudy=["MR"])
    assert set(_pids(r)) == {"SINT-SEM", "SINT-AVILA"}
    assert _pids(_run(patientName="zzteste", modalitiesInStudy=["CT"], startDate="20260101")) == ["SINT-SILVA"]


def test_incremental_por_changes_com_checkpoint(orthanc):
    assert _run(patientName="zzteste novo")["total"] == 0
    orthanc.add(_mk(9001, "ZZTESTE^NOVO JOÃO", "SINT-NOVO", "20261026"))
    r = _run(patientName="novo joao")
    assert _pids(r) == ["SINT-NOVO"]
    conn = worklist_index.connect()
    assert conn.execute("SELECT value FROM worklist_meta WHERE key='changes_seq'").fetchone()[0] == "1"
    conn.close()
    orthanc.delete("1.2.826.0.1.3680043.8.498.9001")
    assert _run(patientName="novo joao")["total"] == 0
    # carga inicial só uma vez: depois, nenhum QIDO paginado sem UID
    before = [c for c in orthanc.calls]
    _run()
    new = orthanc.calls[len(before):]
    assert ("GET", "/changes") in new


def test_so_leitura_e_qido_so_com_uids_da_pagina(orthanc):
    _run(patientName="conceicao")
    n = len(orthanc.calls)
    _run(patientName="conceicao")
    assert all(m == "GET" for m, _ in orthanc.calls)
    assert [p for _, p in orthanc.calls[n:]] == ["/changes", "/dicom-web/studies"]


def test_indice_sem_pixel_e_migracao_aditiva(orthanc):
    _run()
    conn = worklist_index.connect()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(worklist_study)")]
    assert cols == ["study_uid", "orthanc_id", "study_date", "study_time", "name_norm", "modalities",
                    "patient_id", "accession", "description_norm"]
    assert all("DROP" not in s.upper() and "DELETE" not in s.upper() for s in worklist_index.SCHEMA.split(";"))
    conn.close()


def test_validacao(orthanc):
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _run(startDate="2026-01-01")
    with pytest.raises(HTTPException):
        _run(modalitiesInStudy=["CT;DROP"])


def test_exige_sessao_clinica(client):
    assert client.post("/api/worklist/studies", json={"patientName": "zzteste"}).status_code == 401


class SlowOrthanc(FakeOrthanc):
    """Segura a carga inicial depois do 1º lote, para observar o estado de preparação."""

    def __init__(self, studies):
        super().__init__(studies)
        self.gate = __import__("threading").Event()
        self.first_batch = __import__("threading").Event()
        self.loads = 0

    def __call__(self, request):
        qs = parse_qs(urlparse(str(request.url)).query, keep_blank_values=True)
        if request.url.path == "/changes" and "last" in qs:
            self.loads += 1
        if request.url.path == "/statistics":
            return httpx.Response(200, json={"CountStudies": len(self.studies) + self.extra_count})
        if request.url.path == "/dicom-web/studies" and qs.get("offset", ["0"])[0] != "0" and "StudyInstanceUID" not in qs:
            self.first_batch.set()
            self.gate.wait(10)
        return super().__call__(request)


@pytest.fixture
def slow(monkeypatch, tmp_path):
    many = BASE + [_mk(5000 + i, f"ZZTESTE^JOAO {i:05d}", f"SINT-J{i:05d}", "20240101") for i in range(1100)]
    fake = SlowOrthanc(many)

    def factory(*a, **kw):
        kw["transport"] = httpx.MockTransport(fake)
        return _REAL(*a, **kw)

    monkeypatch.setattr(worklist.httpx, "AsyncClient", factory)
    monkeypatch.setattr(worklist.settings, "orthanc_url", "http://orthanc-sintetico.invalid:8042")
    monkeypatch.setattr(worklist.settings, "worklist_index_path", str(tmp_path / "idx.db"))
    worklist_index._set_state(status="idle", indexed=0, total=None)
    yield fake
    fake.gate.set()
    if worklist_index._bg_thread:
        worklist_index._bg_thread.join(10)


def test_preparacao_nao_bloqueia_e_resultado_parcial(slow):
    import time as _t
    t = worklist_index.start_background()
    assert slow.first_batch.wait(10)
    t0 = _t.perf_counter()
    r = _run(patientName="zzteste joao")
    assert _t.perf_counter() - t0 < 1.0  # a busca não espera a carga completa
    assert r["partial"] is True and r["index"]["status"] == "indexing"
    assert r["index"]["indexed"] == 1000 and r["index"]["total"] == len(slow.studies)
    assert 0 < r["total"] < 1101  # só o que já foi indexado
    slow.gate.set()
    t.join(10)
    r = _run(patientName="zzteste joao")
    assert r["partial"] is False and r["index"]["status"] == "ready" and r["total"] == 1101


def test_sincronizacoes_simultaneas_uma_carga_so(slow):
    import threading as _th
    threads = [_th.Thread(target=lambda: _run(patientName="zzteste")) for _ in range(5)]
    first = worklist_index.start_background()
    for th in threads:
        th.start()
    assert worklist_index.start_background() is first  # idempotente enquanto roda
    assert slow.first_batch.wait(10)
    slow.gate.set()
    for th in threads:
        th.join(10)
    first.join(10)
    assert slow.loads == 1  # uma única carga inicial
    assert _run()["index"]["status"] == "ready"


def test_reconstrucao_em_background(orthanc):
    t = worklist_index.start_background(rebuild=True)
    t.join(10)
    assert worklist_index.is_ready() and _run()["total"] == len(BASE)


def test_arquivo_do_indice_0600(orthanc):
    import os
    import stat
    path = worklist_index.index_path()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    os.chmod(path, 0o644)
    worklist_index.connect().close()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600



def test_orthanc_indisponivel_status_error_sem_parcial_e_intervalo(raw_orthanc, monkeypatch):
    import time as _t

    def down(request):
        raise httpx.ConnectError("orthanc fora do ar")

    raw_orthanc.__class__ = type("Down", (FakeOrthanc,), {"__call__": lambda self, req: down(req)})
    monkeypatch.setattr(worklist_index, "_last_attempt", None)
    monkeypatch.setattr(worklist.settings, "worklist_index_retry_seconds", 60)
    t = worklist_index.start_background()
    t.join(10)
    r = _run(patientName="zzteste")
    assert r["index"]["status"] == "error" and r["partial"] is False
    # dentro dos 60 s, a busca não dispara nova carga
    assert worklist_index.start_background() is None
    _run()
    assert worklist_index._bg_thread is t
    # passado o intervalo (configurável), tenta de novo
    monkeypatch.setattr(worklist_index, "_last_attempt", _t.monotonic() - 61)
    t2 = worklist_index.start_background()
    assert t2 is not None and t2 is not t
    t2.join(10)
    assert worklist_index.state()["status"] == "error"


def test_rebuild_limpa_linhas_e_removido_nao_volta(orthanc):
    uid = "1.2.826.0.1.3680043.8.498.4"
    assert _pids(_run(patientId="SINT-SILVA")) == ["SINT-SILVA"]
    # removido do Orthanc SEM evento no /changes (ex.: /changes podado): só o rebuild resolve
    orthanc.studies = [x for x in orthanc.studies if x["uid"] != uid]
    t = worklist_index.start_background(rebuild=True)
    t.join(10)
    conn = worklist_index.connect()
    assert conn.execute("SELECT COUNT(*) FROM worklist_study WHERE study_uid=?", (uid,)).fetchone()[0] == 0
    conn.close()
    r = _run(patientId="SINT-SILVA")
    assert r["total"] == 0 and r["index"]["status"] == "ready"


def test_sync_de_teste_nao_e_usado_por_rotas():
    from pathlib import Path
    app_dir = Path(worklist_index.__file__).parent
    for f in app_dir.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        if f.name != "worklist_index.py":
            assert "_sync_now_for_tests" not in src, f.name
        assert "worklist_index.sync(" not in src, f.name
    assert not hasattr(worklist_index, "sync")



def test_tentar_de_novo_respeita_intervalo_no_backend(raw_orthanc, monkeypatch, client):
    import time as _t
    from fastapi import HTTPException

    raw_orthanc.__class__ = type("Down2", (FakeOrthanc,), {
        "__call__": lambda self, req: (_ for _ in ()).throw(httpx.ConnectError("fora"))})
    monkeypatch.setattr(worklist_index, "_last_attempt", None)
    monkeypatch.setattr(worklist.settings, "worklist_index_retry_seconds", 60)
    worklist_index.start_background().join(10)
    r = _run()
    assert r["index"]["status"] == "error" and 55 <= r["index"]["retryInSeconds"] <= 60
    with pytest.raises(HTTPException) as exc:
        asyncio.run(worklist.worklist_index_retry())
    assert exc.value.status_code == 429 and exc.value.headers["Retry-After"]
    monkeypatch.setattr(worklist_index, "_last_attempt", _t.monotonic() - 61)
    out = asyncio.run(worklist.worklist_index_retry())
    assert out["started"] is True
    worklist_index._bg_thread.join(10)
    # a rota exige sessão clínica
    assert client.post("/api/worklist/index/retry").status_code == 401


def test_indice_vazio_com_orthanc_cheio_reconstroi_sozinho(raw_orthanc):
    """Índice criado com 0 estudos (antes do seed) e /changes sem eventos: o startup reconstrói."""
    estudos = raw_orthanc.studies
    raw_orthanc.studies = []
    asyncio.run(worklist_index._sync_now_for_tests())
    conn = worklist_index.connect()
    assert conn.execute("SELECT COUNT(*) FROM worklist_study").fetchone()[0] == 0
    conn.close()
    raw_orthanc.studies = estudos  # chegaram sem evento no /changes (ex.: podado)
    worklist_index.start_background().join(10)
    r = _run()
    assert r["index"]["status"] == "ready" and r["total"] == len(estudos)


MUITOS = [_mk(5000 + i, f"ZZTESTE^MARIA {i:05d}", f"SINT-LIM-{i:05d}", "20240101") for i in range(300)]


def _meta(key):
    conn = worklist_index.connect()
    try:
        return worklist_index._meta_get(conn, key)
    finally:
        conn.close()


@pytest.mark.parametrize("corte", [100, 101])
def test_carga_aguenta_limitfindresults_do_orthanc(raw_orthanc, corte):
    """Orthanc corta cada consulta em 100/101 (LimitFindResults): a carga indexa TODOS."""
    raw_orthanc.studies = list(MUITOS)
    raw_orthanc.limit_find = corte
    worklist_index.start_background().join(20)
    st = worklist_index.state()
    assert st["status"] == "ready" and st["indexed"] == st["total"] == 300
    assert worklist_index._count_index() == 300 and _meta("full_load_done") == "1"
    r = _run(patientName="maria", limit=50, offset=250)
    assert r["total"] == 300 and len(r["studies"]) == 50


def test_carga_incompleta_nao_fica_ready_nem_grava_full_load_done(raw_orthanc, monkeypatch):
    raw_orthanc.studies = list(MUITOS)
    raw_orthanc.limit_find = 100
    raw_orthanc.extra_count = 7  # /statistics diz 307, o QIDO só entrega 300
    monkeypatch.setattr(worklist_index, "_last_attempt", None)
    worklist_index.start_background().join(20)
    st = worklist_index.state()
    assert st["status"] == "incomplete" and st["indexed"] == 300 and st["total"] == 307
    assert _meta("full_load_done") is None
    r = _run()
    assert r["index"]["status"] == "incomplete" and r["partial"] is False
    assert r["index"]["indexed"] == 300 and r["index"]["total"] == 307


def test_startup_reconstroi_indice_antigo_cortado_em_101(raw_orthanc):
    """Produção hoje: índice gravado com full_load_done e só 101 estudos; o Orthanc tem 300."""
    raw_orthanc.studies = list(MUITOS)
    conn = worklist_index.connect()
    vals = [worklist_index.row_from_qido(_dicom(x)) for x in MUITOS[:101]]
    conn.executemany(worklist_index.UPSERT, vals)
    worklist_index._meta_set(conn, "changes_seq", len(raw_orthanc.changes))
    worklist_index._meta_set(conn, "full_load_done", 1)
    conn.commit()
    conn.close()
    assert worklist_index.is_ready() and worklist_index._count_index() == 101
    raw_orthanc.limit_find = 100
    worklist_index.start_background().join(20)
    st = worklist_index.state()
    assert st["status"] == "ready" and worklist_index._count_index() == 300 and st["total"] == 300
    assert _run(patientId="SINT-LIM-00299")["total"] == 1


def test_incremental_e_rebuild_com_limite_do_orthanc(raw_orthanc):
    raw_orthanc.studies = list(MUITOS)
    raw_orthanc.limit_find = 100
    worklist_index.start_background().join(20)
    raw_orthanc.add(_mk(9999, "ZZTESTE^NOVO", "SINT-NOVO", "20261026"))
    asyncio.run(worklist_index.sync_on_request())
    assert worklist_index._count_index() == 301
    worklist_index.start_background(rebuild=True).join(20)
    assert worklist_index._count_index() == 301 and worklist_index.state()["status"] == "ready"


# --- Follow-up do #9: ressalvas do Tester (1, 2) e LP20 -------------------------------------


@pytest.fixture(autouse=True)
def _sem_timer_entre_testes():
    yield
    worklist_index.cancel_auto_retry()
    if worklist_index._bg_thread:
        worklist_index._bg_thread.join(10)


def _conta_cargas(monkeypatch):
    cargas = []
    real = worklist_index.full_load

    async def contando(client, path=None):
        cargas.append(path)
        return await real(client, path)

    monkeypatch.setattr(worklist_index, "full_load", contando)
    return cargas


def test_backoff_exponencial_com_teto(monkeypatch):
    monkeypatch.setattr(worklist.settings, "worklist_index_retry_seconds", 60)
    monkeypatch.setattr(worklist.settings, "worklist_index_retry_max_seconds", 1800)
    assert [worklist_index.retry_delay(n) for n in range(7)] == [60, 120, 240, 480, 960, 1800, 1800]


def test_incomplete_nova_tentativa_em_background_e_busca_nao_recarrega(raw_orthanc, monkeypatch):
    """Ressalva 1: com o Orthanc cortando, buscas NÃO disparam carga; o timer tenta de novo
    com backoff e, quando o Orthanc entrega tudo, o índice fica ready."""
    import time as _t
    raw_orthanc.studies = list(MUITOS)
    raw_orthanc.limit_find = 100
    raw_orthanc.extra_count = 7
    monkeypatch.setattr(worklist.settings, "worklist_index_auto_retry", True)
    monkeypatch.setattr(worklist.settings, "worklist_index_retry_seconds", 1)
    monkeypatch.setattr(worklist_index, "_last_attempt", None)
    cargas = _conta_cargas(monkeypatch)
    worklist_index.start_background().join(20)
    st = worklist_index.state()
    assert st["status"] == "incomplete" and len(cargas) == 1
    assert st["nextAutoRetryInSeconds"] in (0, 1)
    for _ in range(20):  # várias buscas seguidas: nenhuma recarga por requisição
        r = _run(patientName="maria")
        assert r["total"] == 300 and r["index"]["status"] in ("incomplete", "indexing")
    assert len(cargas) <= 2  # no máximo a tentativa do timer (1 s), nunca uma por busca
    raw_orthanc.extra_count = 0  # Orthanc volta a bater a contagem
    fim = _t.monotonic() + 15
    while worklist_index.state()["status"] != "ready" and _t.monotonic() < fim:
        _t.sleep(0.1)
    assert worklist_index.state()["status"] == "ready" and worklist_index._count_index() == 300
    assert _meta("full_load_done") == "1" and worklist_index.state()["nextAutoRetryInSeconds"] is None
    assert worklist_index._retry_attempts == 0


def test_incomplete_backoff_cresce_entre_tentativas(raw_orthanc, monkeypatch):
    raw_orthanc.studies = list(MUITOS)
    raw_orthanc.extra_count = 7
    monkeypatch.setattr(worklist.settings, "worklist_index_auto_retry", True)
    monkeypatch.setattr(worklist.settings, "worklist_index_retry_seconds", 100)
    worklist_index.start_background().join(20)
    assert worklist_index._retry_attempts == 1 and 99 <= worklist_index.next_auto_retry_in_seconds() <= 100
    worklist_index.start_background(_auto=True).join(20)  # o que o timer faria
    assert worklist_index._retry_attempts == 2 and 199 <= worklist_index.next_auto_retry_in_seconds() <= 200


def test_reconstrucao_em_sombra_busca_continua_com_dados_antigos(raw_orthanc, monkeypatch):
    """Ressalva 2: índice antigo (101, marcado pronto) e Orthanc com 300. Durante a reconstrução
    a busca continua devolvendo os 101 antigos (nada é apagado antes); no fim troca atômica."""
    raw_orthanc.studies = list(MUITOS)
    conn = worklist_index.connect()
    conn.executemany(worklist_index.UPSERT, [worklist_index.row_from_qido(_dicom(x)) for x in MUITOS[:101]])
    worklist_index._meta_set(conn, "changes_seq", 0)
    worklist_index._meta_set(conn, "full_load_done", 1)
    conn.commit()
    conn.close()
    raw_orthanc.__class__ = SlowOrthanc
    raw_orthanc.gate = __import__("threading").Event()
    raw_orthanc.first_batch = __import__("threading").Event()
    raw_orthanc.loads = 0
    raw_orthanc.limit_find = 100
    t = worklist_index.start_background()
    assert raw_orthanc.first_batch.wait(10)
    assert worklist_index.shadow_path().exists()
    r = _run(patientName="maria")
    assert r["total"] == 101  # dados antigos, não lista vazia nem parcial da sombra
    assert _run(patientId="SINT-LIM-00000")["total"] == 1
    raw_orthanc.gate.set()
    t.join(20)
    assert worklist_index.state()["status"] == "ready" and _run(patientName="maria")["total"] == 300
    assert not worklist_index.shadow_path().exists()
    import os
    import stat
    assert stat.S_IMODE(os.stat(worklist_index.index_path()).st_mode) == 0o600


def test_reconstrucao_incompleta_nao_troca_por_menos(raw_orthanc, monkeypatch):
    """Sombra incompleta com MENOS estudos que o índice atual: descarta e mantém o antigo."""
    raw_orthanc.studies = list(MUITOS)
    worklist_index.start_background().join(20)
    assert worklist_index._count_index() == 300
    raw_orthanc.limit_find = 50
    raw_orthanc.studies = list(MUITOS[:120])
    raw_orthanc.extra_count = 500
    worklist_index.start_background(rebuild=True).join(20)
    assert worklist_index.state()["status"] == "incomplete"
    assert worklist_index._count_index() == 300 and not worklist_index.shadow_path().exists()


def test_lp20_indice_sobrevive_ao_restart_sem_carga_completa(raw_orthanc, monkeypatch):
    """LP20: com o índice completo, "reinicia" o portal (estado do processo zerado, mesmo arquivo
    no volume): volta ready com a mesma contagem e SEM nova carga completa."""
    raw_orthanc.studies = list(MUITOS)
    worklist_index.start_background().join(20)
    assert worklist_index.state()["status"] == "ready"
    antes = worklist_index._count_index()
    assert antes == 300
    # restart: novo processo => estado em memória do zero, mesmo worklist_index.db
    monkeypatch.setattr(worklist_index, "_bg_thread", None)
    monkeypatch.setattr(worklist_index, "_last_attempt", None)
    worklist_index._set_state(status="idle", indexed=0, total=None)
    cargas = _conta_cargas(monkeypatch)
    raw_orthanc.calls.clear()
    worklist_index.start_background().join(20)  # o que o startup do portal faz
    st = worklist_index.state()
    assert st["status"] == "ready" and st["indexed"] == st["total"] == antes
    assert cargas == []  # nenhuma carga completa
    paginadas = [p for m, p in raw_orthanc.calls if p == "/dicom-web/studies"]
    assert paginadas == []  # nem QIDO do acervo: só /changes e /statistics
    r = _run(patientId="SINT-LIM-00299")
    assert r["total"] == 1 and r["index"]["status"] == "ready"
