"""Regras da sincronização MWL sem banco real: janela, status, accession e falha da origem.

Nomes e senhas abaixo são sintéticos (prefixo ZZSINT). Nada disso é paciente ou segredo de hospital.
"""
import logging
from datetime import datetime, time, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.config import settings
from app.mwl_drivers import default_port
from app.mwl_fetch import schedule_window
from app.mwl_scheduler import run_mwl_sync
from app.mwl_sql import SYNC_INTERVAL_ENV, get_mwl_sql_config, get_mwl_sync_meta, save_mwl_sql_config, sync_interval_seconds
from app.mwl_sync import worklist_dir

PATIENT = "ZZSINT^JOÃO CONCEIÇÃO"
SECRET = "ZzSenhaSinteticaUnica99"
TODAY = datetime.now(timezone.utc).date()


def _paths(tmp_path, monkeypatch):
    config = tmp_path / "orthanc.json"
    config.write_text("{}\n", encoding="utf-8")
    wl = tmp_path / "worklists"
    wl.mkdir()
    monkeypatch.setattr(settings, "orthanc_config_path", str(config))
    monkeypatch.setattr(settings, "orthanc_worklist_path", str(wl))
    monkeypatch.setenv("LEX_MWL_SQL_PASSWORD", SECRET)
    return wl


def _config(**overrides):
    payload = {
        "enabled": True,
        "driver": "mssql",
        "mode": "custom",
        "host": "127.0.0.1",
        "port": 1,
        "database": "lexmwl_sint",
        "username": "lex_mwl_ro",
        "password_env": "LEX_MWL_SQL_PASSWORD",
        "table": "vw_agenda_sintetica",
        "custom_sql": "SELECT 1 AS accession_number",
        "field_mapping": {
            "status": "status",
            "status_cancelled": "CANCELADO,CANCELADA",
            "status_performed": "REALIZADO,CONCLUIDO",
            "scheduled_date": "scheduled_date",
        },
        "modality_filter": [],
        "modality_routes": [],
        "sync_interval_minutes": 5,
        "schedule_window_days": 7,
        "schedule_timezone": "UTC",
        "login_timeout_seconds": 1,
        "query_timeout_seconds": 5,
    }
    payload.update(overrides)
    save_mwl_sql_config(payload)


def _row(**overrides):
    base = {
        "accession_number": "SINT-OK-1",
        "patient_id": "SINT-PID-1",
        "patient_name": PATIENT,
        "patient_birth_date": datetime(1980, 1, 15).date(),
        "patient_sex": "M",
        "modality": "DX",
        "station_aet": "RX_SALA1",
        "procedure_description": "Tórax sintético",
        "scheduled_date": TODAY,
        "scheduled_time": time(14, 30, 0),
        "study_instance_uid": "1.2.826.0.1.3680043.8.498.700001",
        "status": "AGENDADO",
    }
    base.update(overrides)
    return base


def _patch_rows(monkeypatch, rows):
    def _read(_cfg, limit=None):
        return list(rows)

    monkeypatch.setattr("app.mwl_fetch.read_source_rows", _read)


def _names(directory):
    return sorted(path.name for path in directory.glob("lex-*.wl"))


def test_a2_um_wl_iso_ir_192_com_acento(tmp_path, monkeypatch):
    import pydicom

    _paths(tmp_path, monkeypatch)
    _config()
    _patch_rows(monkeypatch, [_row(study_instance_uid=None)])
    result = run_mwl_sync("teste")
    assert result["synced"] == 1
    assert result["errors"] == 0
    assert _names(worklist_dir()) == ["lex-SINT-OK-1.wl"]

    path = worklist_dir() / "lex-SINT-OK-1.wl"
    raw = path.read_bytes()
    assert "JOÃO".encode("utf-8") in raw
    assert "CONCEIÇÃO".encode("utf-8") in raw
    ds = pydicom.dcmread(path)
    assert "ISO_IR 192" in str(ds.SpecificCharacterSet)
    assert "JOÃO" in str(ds.PatientName)
    assert "CONCEIÇÃO" in str(ds.PatientName)
    assert str(ds.PatientID) == "SINT-PID-1"
    assert str(ds.PatientBirthDate) == "19800115"
    assert str(ds.PatientSex) == "M"
    assert str(ds.AccessionNumber) == "SINT-OK-1"
    assert str(ds.StudyInstanceUID).startswith("2.25.")
    assert "Tórax" in str(ds.RequestedProcedureDescription)
    sps = ds.ScheduledProcedureStepSequence[0]
    assert str(sps.Modality) == "DX"
    assert str(sps.ScheduledStationAETitle) == "RX_SALA1"
    assert str(sps.ScheduledProcedureStepStartDate) == TODAY.strftime("%Y%m%d")
    assert "143000" in "".join(ch for ch in str(sps.ScheduledProcedureStepStartTime) if ch.isdigit())

    again = run_mwl_sync("teste")
    assert again["synced"] == 1
    assert _names(worklist_dir()) == ["lex-SINT-OK-1.wl"]
    ds2 = pydicom.dcmread(path)
    assert str(ds2.StudyInstanceUID) == str(ds.StudyInstanceUID)


def test_a4_remove_cancelado_realizado_e_fora_da_janela(tmp_path, monkeypatch):
    """Janela de N dias = hoje inclusive até D+(N-1). Padrão N=7: D+0..D+6 dentro; D+7 fora."""
    _paths(tmp_path, monkeypatch)
    _config()
    start, end = schedule_window({"schedule_window_days": 7, "schedule_timezone": "UTC"})
    assert start == TODAY
    assert end == TODAY + timedelta(days=6)
    rows = [
        _row(accession_number="SINT-HOJE", scheduled_date=TODAY, status="AGENDADO"),
        _row(accession_number="SINT-D6", scheduled_date=TODAY + timedelta(days=6), status="AGENDADO"),
        _row(accession_number="SINT-D7", scheduled_date=TODAY + timedelta(days=7), status="AGENDADO"),
        _row(accession_number="SINT-DEPOIS", scheduled_date=TODAY + timedelta(days=8), status="AGENDADO"),
        _row(accession_number="SINT-ONTEM", scheduled_date=TODAY - timedelta(days=1), status="AGENDADO"),
        _row(accession_number="SINT-CANCEL", scheduled_date=TODAY, status="CANCELADA"),
        _row(accession_number="SINT-FEITO", scheduled_date=TODAY, status="CONCLUIDO"),
    ]
    _patch_rows(monkeypatch, rows)
    result = run_mwl_sync("teste")
    assert result["read"] == 7
    assert result["errors"] == 0
    assert result["synced"] == 2
    assert _names(worklist_dir()) == ["lex-SINT-D6.wl", "lex-SINT-HOJE.wl"]

    _config(schedule_window_days=1)
    narrowed = run_mwl_sync("teste")
    assert narrowed["removed"] >= 1
    assert _names(worklist_dir()) == ["lex-SINT-HOJE.wl"]


def test_padrao_janela_7_dias_e_intervalo_300s(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    monkeypatch.delenv(SYNC_INTERVAL_ENV, raising=False)
    cfg = get_mwl_sql_config()
    assert cfg["schedule_window_days"] == 7
    assert cfg["schedule_timezone"] == "America/Sao_Paulo"
    assert cfg["sync_interval_minutes"] == 5
    assert sync_interval_seconds(cfg) == 300
    assert default_port("mssql") == 1433

    monkeypatch.setenv(SYNC_INTERVAL_ENV, "120")
    assert sync_interval_seconds(cfg) == 120
    monkeypatch.setenv(SYNC_INTERVAL_ENV, "30")
    assert sync_interval_seconds(cfg) == 60
    monkeypatch.setenv(SYNC_INTERVAL_ENV, "nao-numero")
    assert sync_interval_seconds({"sync_interval_minutes": 5}) == 300
    monkeypatch.delenv(SYNC_INTERVAL_ENV, raising=False)
    assert sync_interval_seconds({"sync_interval_minutes": 10}) == 600


def test_a6_accession_unico_e_campo_nulo_conta_erro(tmp_path, monkeypatch, caplog):
    _paths(tmp_path, monkeypatch)
    _config()
    rows = [
        _row(accession_number="SINT-DUP", procedure_description="Primeira"),
        _row(accession_number="SINT-DUP", procedure_description="Segunda"),
        _row(accession_number="", patient_name=PATIENT),
        _row(accession_number="SINT-SEM-NOME", patient_name=None),
        _row(accession_number="SINT-SEM-NASC", patient_birth_date=None),
    ]
    _patch_rows(monkeypatch, rows)
    caplog.set_level(logging.INFO)
    result = run_mwl_sync("teste")
    assert result["read"] == 5
    assert result["errors"] == 3
    assert result["synced"] == 1
    assert _names(worklist_dir()) == ["lex-SINT-DUP.wl"]
    meta = get_mwl_sync_meta()
    assert meta["last_errors"] == 3
    assert meta["last_read"] == 5
    assert meta["last_written"] == 1
    assert PATIENT not in meta["last_error"]
    assert PATIENT not in caplog.text
    assert SECRET not in caplog.text


def test_a5_falha_da_origem_preserva_wl_e_a_proxima_roda(tmp_path, monkeypatch, caplog):
    wl = _paths(tmp_path, monkeypatch)
    _config()
    _patch_rows(monkeypatch, [_row()])
    run_mwl_sync("teste")
    target = wl / "lex-SINT-OK-1.wl"
    before = target.read_bytes()

    def _down(_cfg, limit=None):
        raise TimeoutError(f"timeout password={SECRET}")

    monkeypatch.setattr("app.mwl_fetch.read_source_rows", _down)
    caplog.set_level(logging.WARNING)
    with pytest.raises(HTTPException) as raised:
        run_mwl_sync("teste")
    assert target.read_bytes() == before
    assert _names(wl) == ["lex-SINT-OK-1.wl"]
    meta = get_mwl_sync_meta()
    assert meta["last_removed"] == 0
    assert meta["last_written"] == 0
    assert meta["last_errors"] == 1
    assert meta["last_at"]
    assert SECRET not in meta["last_error"]
    assert PATIENT not in meta["last_error"]
    assert SECRET not in raised.value.detail
    assert PATIENT not in str(raised.value.detail)
    assert SECRET not in caplog.text
    assert PATIENT not in caplog.text
    text = (tmp_path / "lex-pacs-settings.json").read_text(encoding="utf-8")
    assert SECRET not in text
    assert PATIENT not in text

    _patch_rows(monkeypatch, [_row()])
    again = run_mwl_sync("teste")
    assert again["synced"] == 1
    assert get_mwl_sync_meta()["last_error"] == ""


def test_a5_porta_fechada_nao_apaga_wl_gravado(tmp_path, monkeypatch):
    wl = _paths(tmp_path, monkeypatch)
    intact = wl / "lex-SINT-KEEP.wl"
    intact.write_bytes(b"WL-INTACTO-SINTETICO")
    _config(host="127.0.0.1", port=1, login_timeout_seconds=1)
    with pytest.raises(HTTPException) as raised:
        run_mwl_sync("teste")
    assert intact.read_bytes() == b"WL-INTACTO-SINTETICO"
    assert SECRET not in str(raised.value.detail)
    assert get_mwl_sync_meta()["last_removed"] == 0


def test_status_no_portal_sem_dado_de_paciente(tmp_path, monkeypatch, client):
    _paths(tmp_path, monkeypatch)
    _config()
    _patch_rows(monkeypatch, [_row()])

    async def _plugin_off():
        return False

    monkeypatch.setattr("app.admin.orthanc_mwl_plugin_enabled", _plugin_off)
    login = client.post(
        "/api/auth/clinical/login",
        json={"username": "admin", "password": "Senha-Inicial-123"},
    )
    assert login.status_code == 200, login.text
    changed = client.post(
        "/api/auth/clinical/change-password",
        json={"current_password": "Senha-Inicial-123", "new_password": "Nova-Senha-Admin-456"},
    )
    assert changed.status_code == 200, changed.text

    synced = client.post("/api/admin/pacs/mwl/sync")
    assert synced.status_code == 200, synced.text
    body = synced.json()
    assert body["read"] == 1
    assert body["synced"] == 1
    assert body["errors"] == 0
    assert PATIENT not in synced.text

    status = client.get("/api/admin/pacs/mwl/status")
    assert status.status_code == 200, status.text
    payload = status.json()
    sync = payload["sync"]
    assert sync["last_read"] == 1
    assert sync["last_written"] == 1
    assert sync["last_removed"] == 0
    assert sync["last_errors"] == 0
    assert sync["last_at"]
    for marker in (PATIENT, "SINT-PID-1", "19800115", "1980-01-15", SECRET, "JOÃO", "CONCEIÇÃO"):
        assert marker not in status.text

    def _down(_cfg, limit=None):
        raise ConnectionError("origem fora do ar")

    monkeypatch.setattr("app.mwl_fetch.read_source_rows", _down)
    failed = client.post("/api/admin/pacs/mwl/sync")
    assert failed.status_code == 503
    assert PATIENT not in failed.text
    assert SECRET not in failed.text
    down = client.get("/api/admin/pacs/mwl/status")
    assert down.status_code == 200
    assert down.json()["sync"]["last_error"]
    assert down.json()["sync"]["last_removed"] == 0
    assert down.json()["entries_total"] == 1
    assert PATIENT not in down.text


def test_fuso_invalido_rejeitado(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    with pytest.raises(HTTPException) as raised:
        _config(schedule_timezone="Nao/Existe")
    assert raised.value.status_code == 400
