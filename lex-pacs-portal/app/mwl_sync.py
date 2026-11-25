from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException
from pydicom.dataset import Dataset, FileDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from .config import settings
from .mwl_fetch import load_mwl_sync_plan
from .mwl_sql import get_mwl_sql_config
from .pacs_config import _read_config as read_orthanc_config, _write_config as write_orthanc_config

logger = logging.getLogger("lex_pacs.mwl_sync")

MWL_PLUGIN = "/usr/local/share/orthanc/plugins/libModalityWorklists.so"
_SECRET_ENV = re.compile(r"(PASSWORD|SECRET|TOKEN|PWD)", re.IGNORECASE)
_SECRET_ASSIGN = re.compile(r"(?i)(password|pwd|senha)\s*[:=]\s*\S+")


def worklist_dir() -> Path:
    return Path(settings.orthanc_worklist_path)


def sanitize_mwl_error(exc: BaseException, cfg: dict[str, Any] | None = None) -> str:
    """Texto de erro sem senha e sem payload da linha (não inclui dado de paciente)."""
    if isinstance(exc, HTTPException):
        text = str(exc.detail or "")
    else:
        text = f"{type(exc).__name__}: {exc}"
    text = " ".join(text.split())
    secrets: list[str] = []
    if cfg:
        env_name = str(cfg.get("password_env") or "")
        if env_name:
            secrets.append(os.environ.get(env_name, ""))
    for key, value in os.environ.items():
        if value and _SECRET_ENV.search(key):
            secrets.append(value)
    for secret in secrets:
        if secret and len(secret) >= 3:
            text = text.replace(secret, "***")
    text = _SECRET_ASSIGN.sub(r"\1=***", text)
    text = text.strip() or "Falha na origem SQL da worklist."
    return text[:240]


def ensure_mwl_plugin_config() -> bool:
    config = read_orthanc_config()
    plugins = list(config.get("Plugins", []))
    changed = False
    if MWL_PLUGIN not in plugins:
        plugins.append(MWL_PLUGIN)
        config["Plugins"] = plugins
        changed = True
    directory = worklist_dir()
    worklists = config.get("Worklists", {})
    desired = {
        "Enable": True,
        "FilterIssuerAet": False,
        "LimitAnswers": 0,
        "Database": str(directory),
    }
    if worklists != desired:
        config["Worklists"] = desired
        changed = True
    if changed:
        write_orthanc_config(config)
    directory.mkdir(parents=True, exist_ok=True)
    return changed


def _worklist_filename(accession: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", accession)[:48] or "entry"
    return f"lex-{cleaned}.wl"


def _write_worklist_file(row: dict[str, Any]) -> Path:
    accession = str(row.get("accession_number", "")).strip()
    target = worklist_dir() / _worklist_filename(accession)
    target.parent.mkdir(parents=True, exist_ok=True)

    scheduled_date = row.get("scheduled_date")
    if hasattr(scheduled_date, "strftime"):
        date_str = scheduled_date.strftime("%Y%m%d")
    else:
        date_str = str(scheduled_date or "").replace("-", "")[:8]
    time_str = str(row.get("scheduled_time") or "").strip()
    description = str(row.get("procedure_description") or "")
    birth = str(row.get("patient_birth_date") or "").replace("-", "")[:8]
    modality = str(row.get("modality", "")).strip().upper()
    station = str(row.get("station_aet", "")).strip().upper()

    sps = Dataset()
    sps.Modality = modality
    sps.ScheduledStationAETitle = station
    sps.ScheduledProcedureStepStartDate = date_str
    sps.ScheduledProcedureStepStartTime = time_str
    sps.ScheduledProcedureStepDescription = description[:64]

    ds = FileDataset(str(target), {}, preamble=b"\0" * 128)
    ds.is_little_endian = True
    ds.is_implicit_vr = False
    ds.file_meta = Dataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.31"
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()

    # ISO_IR 192 (UTF-8) antes dos nomes, para o acento não virar lixo no aparelho.
    ds.SpecificCharacterSet = "ISO_IR 192"
    ds.SOPClassUID = "1.2.840.10008.5.1.4.31"
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
    ds.PatientName = str(row.get("patient_name") or "")
    ds.PatientID = str(row.get("patient_id") or "")
    ds.PatientBirthDate = birth
    ds.PatientSex = str(row.get("patient_sex") or "")
    ds.AccessionNumber = accession
    ds.StudyInstanceUID = str(row.get("study_instance_uid") or "")
    ds.RequestedProcedureDescription = description[:64]
    ds.ScheduledProcedureStepSequence = Sequence([sps])

    ds.save_as(str(target), write_like_original=False)
    return target


def count_lex_worklists() -> int:
    directory = worklist_dir()
    if not directory.is_dir():
        return 0
    return sum(1 for _ in directory.glob("lex-*.wl"))


def remove_worklist_file(accession: str) -> bool:
    accession = str(accession or "").strip()
    if not accession:
        return False
    target = worklist_dir() / _worklist_filename(accession)
    if not target.is_file():
        return False
    try:
        target.unlink()
        return True
    except OSError:
        return False


def sync_mwl_from_sql() -> dict[str, Any]:
    """Lê a origem primeiro. Só mexe nos .wl depois de uma leitura bem-sucedida."""
    cfg = get_mwl_sql_config()
    if not cfg.get("enabled", True):
        raise RuntimeError("Sync SQL MWL desabilitado.")
    plan = load_mwl_sync_plan()
    ensure_mwl_plugin_config()

    directory = worklist_dir()
    directory.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    keep: set[str] = set()
    for row in plan.rows_to_write:
        path = _write_worklist_file(row)
        written.append(path.name)
        keep.add(path.name)

    removed = 0
    for path in directory.glob("lex-*.wl"):
        if path.name in keep:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue

    if plan.errors:
        logger.warning(
            "MWL sync: %s item(ns) pulados (accession vazio ou campo obrigatório nulo)",
            plan.errors,
        )
    return {
        "removed": removed,
        "synced": len(written),
        "read": plan.read,
        "errors": plan.errors,
        "files": written,
        "worklist_dir": str(directory),
        "error_summary": plan.error_summary,
    }


def list_mwl_entries(station_aet: str = "") -> list[dict[str, Any]]:
    rows = load_mwl_sync_plan().rows_to_write
    station = station_aet.strip().upper()
    entries = []
    for row in rows:
        entry = {
            "accession_number": row.get("accession_number", ""),
            "patient_id": row.get("patient_id", ""),
            "patient_name": row.get("patient_name", ""),
            "modality": row.get("modality", ""),
            "station_aet": row.get("station_aet", ""),
            "procedure_description": row.get("procedure_description", ""),
            "scheduled_date": str(row.get("scheduled_date", "")),
        }
        if station and str(entry["station_aet"]).upper() != station:
            continue
        entries.append(entry)
    return entries


async def orthanc_mwl_plugin_enabled() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0, auth=settings.orthanc_auth) as client:
            response = await client.get(f"{settings.orthanc_url}/plugins")
            response.raise_for_status()
            plugins = response.json()
            return any("worklist" in str(item).lower() for item in plugins)
    except httpx.HTTPError:
        return False
