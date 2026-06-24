from __future__ import annotations

import logging
import threading
from typing import Any

from pydicom.dataset import Dataset

from .audit import log_event
from .mpps_settings import get_mpps_config, record_mpps_event
from .mwl_store import delete_mwl_row
from .mwl_sync import remove_worklist_file

logger = logging.getLogger("lex_pacs.mpps")

_lock = threading.Lock()
_instances: dict[str, Dataset] = {}


def extract_accession(ds: Dataset) -> str:
    accession = str(getattr(ds, "AccessionNumber", "") or "").strip()
    if accession:
        return accession[:32]

    seq = getattr(ds, "ScheduledStepAttributesSequence", None)
    if seq:
        for item in seq:
            accession = str(getattr(item, "AccessionNumber", "") or "").strip()
            if accession:
                return accession[:32]

    perf = getattr(ds, "PerformedSeriesSequence", None)
    if perf:
        for series in perf:
            ref = getattr(series, "ReferencedStudySequence", None)
            if not ref:
                continue
            for study in ref:
                accession = str(getattr(study, "AccessionNumber", "") or "").strip()
                if accession:
                    return accession[:32]
    return ""


def _should_complete_mwl(status: str) -> bool:
    cfg = get_mpps_config()
    if not cfg.get("auto_complete_mwl", True):
        return False
    normalized = status.strip().upper()
    if normalized == "COMPLETED":
        return True
    return normalized == "DISCONTINUED" and bool(cfg.get("complete_on_discontinued"))


def complete_mwl_for_mpps(*, accession: str, status: str, actor: str) -> dict[str, Any]:
    accession = accession.strip()[:32]
    if not accession:
        record_mpps_event(status=status, actor=actor, error="Accession ausente no MPPS.")
        return {"applied": False, "reason": "missing_accession"}

    if not _should_complete_mwl(status):
        record_mpps_event(accession=accession, status=status, actor=actor)
        return {"applied": False, "reason": "status_ignored"}

    deleted = delete_mwl_row(accession)
    file_removed = remove_worklist_file(accession)
    record_mpps_event(
        accession=accession,
        status=status,
        actor=actor,
        mwl_removed=deleted or file_removed,
    )
    log_event(
        "mpps_complete",
        actor,
        accession=accession,
        status=status,
        mwl_deleted=deleted,
        wl_removed=file_removed,
    )
    return {
        "applied": True,
        "accession": accession,
        "mwl_deleted": deleted,
        "worklist_file_removed": file_removed,
    }


def on_mpps_create(event: Any) -> tuple[int, Dataset | None]:
    req = event.request
    uid = str(getattr(req, "AffectedSOPInstanceUID", "") or "").strip()
    if not uid:
        return 0x0106, None

    with _lock:
        if uid in _instances:
            return 0x0111, None

    attr_list = event.attribute_list
    status = str(getattr(attr_list, "PerformedProcedureStepStatus", "") or "").strip().upper()
    if status != "IN PROGRESS":
        return 0x0106, None

    ds = Dataset()
    ds.SOPClassUID = req.AffectedSOPClassUID or "1.2.840.10008.3.1.2.3.3"
    ds.SOPInstanceUID = uid
    ds.update(attr_list)

    with _lock:
        _instances[uid] = ds

    accession = extract_accession(ds)
    record_mpps_event(accession=accession, status=status, actor="mpps:n-create")
    log_event("mpps_create", "mpps", accession=accession, sop_instance_uid=uid[:64])
    return 0x0000, ds


def on_mpps_set(event: Any) -> tuple[int, Dataset | None]:
    req = event.request
    uid = str(getattr(req, "RequestedSOPInstanceUID", "") or "").strip()
    with _lock:
        ds = _instances.get(uid)
    if ds is None:
        return 0x0112, None

    mod_list = event.attribute_list
    ds.update(mod_list)
    status = str(getattr(ds, "PerformedProcedureStepStatus", "") or "").strip().upper()
    accession = extract_accession(ds)

    with _lock:
        _instances[uid] = ds

    result = complete_mwl_for_mpps(accession=accession, status=status, actor="mpps:n-set")
    log_event(
        "mpps_set",
        "mpps",
        accession=accession,
        status=status,
        mwl_applied=result.get("applied", False),
    )

    if status in {"COMPLETED", "DISCONTINUED"}:
        with _lock:
            _instances.pop(uid, None)

    return 0x0000, ds


def simulate_mpps_complete(accession: str, *, actor: str) -> dict[str, Any]:
    return complete_mwl_for_mpps(accession=accession, status="COMPLETED", actor=actor)
