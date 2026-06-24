from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
from pydicom.dataset import Dataset, FileDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from .config import settings
from .mwl_fetch import fetch_mwl_source_rows
from .pacs_config import _read_config as read_orthanc_config, _write_config as write_orthanc_config

MWL_PLUGIN = "/usr/local/share/orthanc/plugins/libModalityWorklists.so"
WORKLIST_DIR = Path(settings.orthanc_worklist_path)


def ensure_mwl_plugin_config() -> bool:
    config = read_orthanc_config()
    plugins = list(config.get("Plugins", []))
    changed = False
    if MWL_PLUGIN not in plugins:
        plugins.append(MWL_PLUGIN)
        config["Plugins"] = plugins
        changed = True
    worklists = config.get("Worklists", {})
    desired = {
        "Enable": True,
        "FilterIssuerAet": False,
        "LimitAnswers": 0,
        "Database": str(WORKLIST_DIR),
    }
    if worklists != desired:
        config["Worklists"] = desired
        changed = True
    if changed:
        write_orthanc_config(config)
    WORKLIST_DIR.mkdir(parents=True, exist_ok=True)
    return changed


def _write_worklist_file(row: dict[str, Any]) -> Path:
    accession = str(row.get("accession_number", "")).strip()
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", accession)[:48] or "entry"
    filename = f"lex-{cleaned}.wl"
    target = WORKLIST_DIR / filename

    scheduled_date = row.get("scheduled_date")
    if hasattr(scheduled_date, "strftime"):
        date_str = scheduled_date.strftime("%Y%m%d")
    else:
        date_str = str(scheduled_date or "").replace("-", "")[:8]

    sps = Dataset()
    sps.AccessionNumber = accession
    sps.Modality = str(row.get("modality", "")).strip().upper()
    sps.ScheduledStationAETitle = str(row.get("station_aet", "")).strip().upper()
    sps.ScheduledProcedureStepStartDate = date_str
    sps.ScheduledProcedureStepDescription = str(row.get("procedure_description", ""))[:64]

    ds = FileDataset(str(target), {}, preamble=b"\0" * 128)
    ds.is_little_endian = True
    ds.is_implicit_vr = False
    ds.file_meta = Dataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.31"
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()

    ds.SOPClassUID = "1.2.840.10008.5.1.4.31"
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
    ds.PatientID = str(row.get("patient_id", ""))
    ds.PatientName = str(row.get("patient_name", ""))
    ds.AccessionNumber = accession
    ds.ScheduledProcedureStepSequence = Sequence([sps])
    ds.ScheduledStationAETitle = sps.ScheduledStationAETitle

    ds.save_as(str(target), write_like_original=False)
    return target


def _purge_lex_worklists() -> int:
    removed = 0
    if not WORKLIST_DIR.is_dir():
        return removed
    for path in WORKLIST_DIR.glob("lex-*.wl"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def remove_worklist_file(accession: str) -> bool:
    accession = str(accession or "").strip()
    if not accession:
        return False
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", accession)[:48] or "entry"
    target = WORKLIST_DIR / f"lex-{cleaned}.wl"
    if not target.is_file():
        return False
    try:
        target.unlink()
        return True
    except OSError:
        return False


def fetch_sql_rows() -> list[dict[str, Any]]:
    return fetch_mwl_source_rows()


def sync_mwl_from_sql() -> dict[str, Any]:
    ensure_mwl_plugin_config()
    removed = _purge_lex_worklists()
    rows = fetch_sql_rows()
    created: list[str] = []
    for row in rows:
        path = _write_worklist_file(row)
        created.append(path.name)
    return {
        "removed": removed,
        "synced": len(created),
        "files": created,
        "worklist_dir": str(WORKLIST_DIR),
    }


def list_mwl_entries(station_aet: str = "") -> list[dict[str, Any]]:
    rows = fetch_sql_rows()
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
        if station and entry["station_aet"].upper() != station:
            continue
        entries.append(entry)
    return entries


async def orthanc_mwl_plugin_enabled() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.orthanc_url}/plugins")
            response.raise_for_status()
            plugins = response.json()
            return any("worklist" in str(item).lower() for item in plugins)
    except httpx.HTTPError:
        return False
