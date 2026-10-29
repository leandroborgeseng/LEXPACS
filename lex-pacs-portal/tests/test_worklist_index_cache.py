"""Índice persistente da lista (factory/indice-cache) — só Orthanc FALSO e dados ZZTESTE.

Abrir o app / nova instância reaproveita o índice salvo (sem 'rebuilding', sem QIDO do acervo);
incremental pelo /changes; reconstrução só após N divergências e na janela noturna; trava flock.
"""
import asyncio
import os
import signal
import subprocess
import sys
import textwrap
import time
from datetime import datetime

import httpx
import pytest

from app import worklist_index
from test_worklist import BASE, FakeOrthanc, _conta_cargas, _mk, _run
import test_worklist
from app.worklist_index import orthanc_study_id

raw_orthanc = test_worklist.raw_orthanc  # fixture compartilhada (Orthanc falso)

DENTRO = datetime(2026, 10, 30, 3, 0)
FORA = datetime(2026, 10, 30, 14, 0)


def _at(dt):
    return dt.replace(tzinfo=worklist_index._tz())


def _qido_acervo(calls):
    return [p for m, p in calls if p == "/dicom-web/studies"]


def _restart(monkeypatch):
    """Novo processo: estado em memória do zero, mesmo arquivo no volume."""
    monkeypatch.setattr(worklist_index, "_bg_thread", None)
    monkeypatch.setattr(worklist_index, "_last_attempt", None)
    monkeypatch.setattr(worklist_index, "_last_sync", None)
    monkeypatch.setattr(worklist_index, "_last_check", None)
    worklist_index._set_state(status="idle", indexed=0, total=None)


def _grava_estados(monkeypatch):
    vistos = []
    real = worklist_index._set_state

    def spy(**kw):
        if "status" in kw:
            vistos.append(kw["status"])
        real(**kw)

    monkeypatch.setattr(worklist_index, "_set_state", spy)
    return vistos


def _tick(dt=DENTRO, check=True):
    if check:
        worklist_index._last_check = None
    else:
        worklist_index._last_check = time.monotonic()
    return asyncio.run(worklist_index.scheduled_tick(now=_at(dt)))


@pytest.fixture(autouse=True)
def _join_bg():
    yield
    worklist_index.cancel_auto_retry()
    if worklist_index._bg_thread:
        worklist_index._bg_thread.join(10)


def test_segunda_abertura_reaproveita_indice_sem_qido_sem_aviso_e_mais_rapida(raw_orthanc, monkeypatch):
    raw_orthanc.studies = BASE + [_mk(7000 + i, f"ZZTESTE^CARGA {i:05d}", f"SINT-C{i:05d}", "20240101")
                                  for i in range(2000)]
    t0 = time.perf_counter()
    worklist_index.start_background().join(30)
    t1 = time.perf_counter() - t0
    assert worklist_index.state()["status"] == "ready"
    n = worklist_index._count_index()

    _restart(monkeypatch)
    estados = _grava_estados(monkeypatch)
    cargas = _conta_cargas(monkeypatch)
    raw_orthanc.calls.clear()
    t0 = time.perf_counter()
    worklist_index.start_background().join(30)
    t2 = time.perf_counter() - t0
    print(f"1ª abertura {t1 * 1000:.1f} ms, 2ª abertura {t2 * 1000:.1f} ms")
    assert _qido_acervo(raw_orthanc.calls) == [] and cargas == []
    assert raw_orthanc.calls == [("GET", "/changes")]  # só o incremental (nada novo)
    assert "rebuilding" not in estados and "indexing" not in estados
    assert worklist_index.state()["status"] == "ready" and worklist_index._count_index() == n
    assert t2 < t1 / 5
    # duas abas: duas buscas, nenhuma carga e nenhum aviso
    for _ in range(2):
        r = _run(patientName="zzteste carga", limit=5)
        assert r["index"]["status"] == "ready" and r["partial"] is False
    assert cargas == [] and "rebuilding" not in estados


def test_sincronizacoes_simultaneas_so_uma_roda(raw_orthanc):
    asyncio.run(worklist_index._sync_now_for_tests())
    with worklist_index.sync_guard() as g:
        assert g.acquired
        assert _tick() == "skipped_locked"
        assert worklist_index.start_background() is not None
        worklist_index._bg_thread.join(10)
        with worklist_index.sync_guard() as g2:
            assert not g2.acquired
    import threading
    gate, entrou = threading.Event(), threading.Event()
    real = raw_orthanc.__class__.__call__

    def lento(self, req):
        if req.url.path == "/changes":
            entrou.set()
            gate.wait(10)
        return real(self, req)

    raw_orthanc.__class__ = type("Lento", (FakeOrthanc,), {"__call__": lento})
    res = []
    th = threading.Thread(target=lambda: res.append(_tick(check=False)))
    th.start()
    assert entrou.wait(10)
    res.append(_tick(check=False))
    gate.set()
    th.join(10)
    assert sorted(res) == ["incremental", "skipped_locked"]


def test_sem_mudancas_nenhuma_chamada_extra_nem_escrita(raw_orthanc):
    asyncio.run(worklist_index._sync_now_for_tests())
    db = worklist_index.index_path()
    antes = (os.stat(db).st_mtime_ns, os.stat(db).st_size)
    time.sleep(0.02)
    raw_orthanc.calls.clear()
    assert _tick(check=False) == "incremental"
    assert raw_orthanc.calls == [("GET", "/changes")]
    assert (os.stat(db).st_mtime_ns, os.stat(db).st_size) == antes


def test_busca_so_sincroniza_se_a_ultima_for_antiga(raw_orthanc, monkeypatch):
    asyncio.run(worklist_index._sync_now_for_tests())
    monkeypatch.setattr(worklist_index.settings, "worklist_index_search_sync_seconds", 30)
    raw_orthanc.calls.clear()
    _run(patientName="zzteste")
    _run(patientName="zzteste")
    assert [p for _, p in raw_orthanc.calls if p == "/changes"] == []  # sincronizou há < 30 s
    monkeypatch.setattr(worklist_index, "_last_sync", time.monotonic() - 31)
    _run(patientName="zzteste")
    assert [p for _, p in raw_orthanc.calls if p == "/changes"] == ["/changes"]


def test_divergencia_1_e_2_nao_reconstroi_3_reconstroi_na_janela_uma_vez(raw_orthanc, monkeypatch, capsys):
    asyncio.run(worklist_index._sync_now_for_tests())
    raw_orthanc.extra_count = 5  # /statistics com 5 a mais que o QIDO (divergência permanente)
    cargas = _conta_cargas(monkeypatch)
    assert _tick(DENTRO) == "incremental+check"
    assert _tick(DENTRO) == "incremental+check"
    assert cargas == [] and worklist_index.rebuild_pending() is None
    assert _tick(FORA) == "incremental+check"  # 3ª: agenda, mas fora da janela não roda
    assert cargas == [] and "3x" in worklist_index.rebuild_pending()
    assert _tick(FORA, check=False) == "incremental"
    assert _tick(DENTRO, check=False) == "incremental+rebuild"
    assert len(cargas) == 1
    out = capsys.readouterr().out
    assert "reconstruindo em sombra, motivo: contagem divergente 3x" in out
    conn = worklist_index.connect()
    assert worklist_index._meta_get(conn, "last_rebuild_reason").startswith("contagem divergente 3x")
    assert worklist_index._meta_get(conn, "accepted_diff") == "5"
    conn.close()
    # não repete: nem em restarts, nem nas próximas conferências (diferença já aceita)
    for _ in range(2):
        _restart(monkeypatch)
        worklist_index.start_background().join(10)
    for _ in range(4):
        _tick(DENTRO)
    assert len(cargas) == 1 and worklist_index.rebuild_pending() is None


def test_compara_orthanc_id_distintos(raw_orthanc):
    asyncio.run(worklist_index._sync_now_for_tests())
    for _ in range(3):
        _tick(FORA)
    assert worklist_index.rebuild_pending() is None  # contagens iguais: sem divergência


def test_volume_ausente_avisa_e_nao_entra_em_loop_de_carga(raw_orthanc, monkeypatch, capsys):
    monkeypatch.setattr(worklist_index, "storage_is_persistent", lambda: False)
    monkeypatch.setattr(worklist_index, "_ephemeral_warned", False)
    monkeypatch.setattr(worklist_index.settings, "worklist_index_auto_retry", True)
    cargas = _conta_cargas(monkeypatch)
    for _ in range(3):  # três "restarts"
        _restart(monkeypatch)
        worklist_index.start_background().join(10)
        assert worklist_index._retry_timer is None or not worklist_index._retry_timer.is_alive()
    assert cargas == [] and _qido_acervo(raw_orthanc.calls) == []
    assert worklist_index.state()["status"] == "error"
    assert "WARNING worklist_index: índice em caminho NÃO persistente" in capsys.readouterr().out
    monkeypatch.setattr(worklist_index.settings, "worklist_index_allow_ephemeral", True)
    _restart(monkeypatch)
    worklist_index.start_background().join(10)
    assert len(cargas) == 1 and worklist_index.state()["status"] == "ready"


def test_deteccao_de_volume(monkeypatch):
    monkeypatch.undo()  # sem o patch do conftest
    monkeypatch.setattr(worklist_index, "_mount_of", lambda p: ("/", "overlay"))
    assert worklist_index.storage_is_persistent() is False
    monkeypatch.setattr(worklist_index, "_mount_of", lambda p: ("/lex-data", "ext4"))
    assert worklist_index.storage_is_persistent() is True
    monkeypatch.setattr(worklist_index, "_mount_of", lambda p: None)
    assert worklist_index.storage_is_persistent() is True


def test_zzteste_newstudy_entra_so_pelo_incremental(raw_orthanc, monkeypatch):
    asyncio.run(worklist_index._sync_now_for_tests())
    cargas = _conta_cargas(monkeypatch)
    s = _mk(9500, "ZZTESTE^INCREMENTAL", "SINT-INCR", "20261029")
    raw_orthanc.studies.append(s)
    raw_orthanc.changes.append({"Seq": len(raw_orthanc.changes) + 1, "ChangeType": "NewStudy",
                                "ResourceType": "Study", "ID": orthanc_study_id(s["pid"], s["uid"])})
    raw_orthanc.calls.clear()
    assert _tick(check=False) == "incremental"
    assert cargas == [] and _qido_acervo(raw_orthanc.calls) == ["/dicom-web/studies"]  # só por UID
    assert _run(patientId="SINT-INCR")["total"] == 1
    assert all(m == "GET" for m, _ in raw_orthanc.calls)


def test_zzteste_deleted_sai_pelo_incremental_sem_reconstrucao(raw_orthanc, monkeypatch):
    asyncio.run(worklist_index._sync_now_for_tests())
    cargas = _conta_cargas(monkeypatch)
    raw_orthanc.delete("1.2.826.0.1.3680043.8.498.4")
    assert _tick(check=False) == "incremental"
    assert cargas == [] and worklist_index.search(
        name=None, wildcard=False, patient_id="SINT-SILVA", accession=None, description=None,
        date_from=None, date_to=None, modalities=[], limit=10, offset=0)[1] == 0


def test_orthanc_fora_no_startup_com_indice_salvo_segue_ready(raw_orthanc, monkeypatch, capsys):
    asyncio.run(worklist_index._sync_now_for_tests())
    _restart(monkeypatch)
    estados = _grava_estados(monkeypatch)
    raw_orthanc.__class__ = type("Fora", (FakeOrthanc,), {"__call__": lambda self, r: httpx.Response(503)})
    worklist_index.start_background().join(10)
    assert worklist_index.state()["status"] == "ready"
    assert "incremental falhou (HTTPStatusError); segue com o índice salvo" in capsys.readouterr().out
    st = asyncio.run(worklist_index.sync_on_request())  # busca não quebra
    assert st["status"] == "ready"
    _, total = worklist_index.search(name="zzteste", wildcard=True, patient_id=None, accession=None,
                                     description=None, date_from=None, date_to=None, modalities=[],
                                     limit=10, offset=0)
    assert total > 0
    assert _tick() == "error" and worklist_index.state()["status"] == "ready"
    assert "rebuilding" not in estados and "error" not in estados


def test_trava_de_processo_morto_por_kill_9_e_liberada(raw_orthanc, tmp_path):
    lock = worklist_index.lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    code = textwrap.dedent(f"""
        import fcntl, os, sys, time
        fd = os.open({str(lock)!r}, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        print("ok", flush=True)
        time.sleep(60)
    """)
    p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().strip() == "ok"
        with worklist_index.sync_guard() as g:
            assert not g.acquired  # outro processo segura a trava
        os.kill(p.pid, signal.SIGKILL)
        p.wait(10)
    finally:
        if p.poll() is None:
            p.kill()
    with worklist_index.sync_guard() as g:
        assert g.acquired  # o kernel liberou o flock com a morte do processo


def test_janela_noturna():
    assert worklist_index.in_rebuild_window(_at(DENTRO))
    assert not worklist_index.in_rebuild_window(_at(FORA))
    assert not worklist_index.in_rebuild_window(_at(datetime(2026, 10, 30, 5, 0)))
