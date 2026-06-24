from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException, status

from .mwl_sql import _read_raw, _write_raw, utc_now_iso

DEFAULT_MPPS = {
    "enabled": True,
    "listen_host": "0.0.0.0",
    "listen_port": 4243,
    "aet": "LEXMPPS",
    "auto_complete_mwl": True,
    "complete_on_discontinued": False,
}


def get_mpps_config() -> dict[str, Any]:
    data = _read_raw()
    cfg = deepcopy(DEFAULT_MPPS)
    cfg.update(data.get("mpps") or {})
    cfg["enabled"] = bool(cfg.get("enabled", True))
    cfg["listen_port"] = int(cfg.get("listen_port") or 4243)
    cfg["aet"] = str(cfg.get("aet") or "LEXMPPS").strip().upper()[:16] or "LEXMPPS"
    cfg["listen_host"] = str(cfg.get("listen_host") or "0.0.0.0").strip() or "0.0.0.0"
    cfg["auto_complete_mwl"] = bool(cfg.get("auto_complete_mwl", True))
    cfg["complete_on_discontinued"] = bool(cfg.get("complete_on_discontinued", False))
    return cfg


def save_mpps_config(payload: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(payload.get("enabled", True))
    listen_host = str(payload.get("listen_host", "0.0.0.0")).strip() or "0.0.0.0"
    listen_port = int(payload.get("listen_port", 4243))
    aet = str(payload.get("aet", "LEXMPPS")).strip().upper()[:16] or "LEXMPPS"
    auto_complete = bool(payload.get("auto_complete_mwl", True))
    complete_disc = bool(payload.get("complete_on_discontinued", False))

    if listen_port < 1 or listen_port > 65535:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Porta MPPS inválida.")
    if listen_port == 4242:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use uma porta diferente da 4242 (Orthanc DICOM).",
        )

    data = _read_raw()
    stats = data.get("mpps_stats") or {}
    data["mpps"] = {
        "enabled": enabled,
        "listen_host": listen_host,
        "listen_port": listen_port,
        "aet": aet,
        "auto_complete_mwl": auto_complete,
        "complete_on_discontinued": complete_disc,
    }
    data["mpps_stats"] = stats
    _write_raw(data)
    return get_mpps_config()


def get_mpps_stats() -> dict[str, Any]:
    data = _read_raw()
    stats = dict(data.get("mpps_stats") or {})
    return {
        "messages_total": int(stats.get("messages_total") or 0),
        "completed_total": int(stats.get("completed_total") or 0),
        "mwl_removed_total": int(stats.get("mwl_removed_total") or 0),
        "last_at": str(stats.get("last_at") or ""),
        "last_accession": str(stats.get("last_accession") or ""),
        "last_status": str(stats.get("last_status") or ""),
        "last_actor": str(stats.get("last_actor") or ""),
        "last_error": str(stats.get("last_error") or ""),
    }


def record_mpps_event(
    *,
    accession: str = "",
    status: str = "",
    actor: str = "",
    mwl_removed: bool = False,
    error: str = "",
) -> dict[str, Any]:
    data = _read_raw()
    stats = dict(data.get("mpps_stats") or {})
    stats["messages_total"] = int(stats.get("messages_total") or 0) + 1
    stats["last_at"] = utc_now_iso()
    if accession:
        stats["last_accession"] = accession[:32]
    if status:
        stats["last_status"] = status[:32]
    if actor:
        stats["last_actor"] = actor[:64]
    if mwl_removed:
        stats["mwl_removed_total"] = int(stats.get("mwl_removed_total") or 0) + 1
    if status.upper() in {"COMPLETED", "DISCONTINUED"}:
        stats["completed_total"] = int(stats.get("completed_total") or 0) + 1
    stats["last_error"] = error[:240]
    data["mpps_stats"] = stats
    _write_raw(data)
    return get_mpps_stats()
