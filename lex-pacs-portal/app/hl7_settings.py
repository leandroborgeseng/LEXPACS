from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from fastapi import HTTPException, status

from .config import settings
from .mwl_sql import _read_raw, _write_raw

DEFAULT_HL7_ORM = {
    "enabled": True,
    "listen_host": "0.0.0.0",
    "listen_port": 2575,
    "auto_sync": True,
    "map_modality_to_station": True,
    "default_station_aet": "",
    "sending_application": "LEXPACS",
    "sending_facility": "LEX",
}


def get_hl7_config() -> dict[str, Any]:
    data = _read_raw()
    cfg = deepcopy(data.get("hl7_orm") or DEFAULT_HL7_ORM)
    for key, value in DEFAULT_HL7_ORM.items():
        cfg.setdefault(key, value)
    # Variáveis de ambiente só definem o bootstrap inicial (antes da 1ª gravação na UI).
    if "hl7_orm" not in data:
        if settings.hl7_orm_enabled is not None:
            cfg["enabled"] = settings.hl7_orm_enabled
        if settings.hl7_orm_port:
            cfg["listen_port"] = settings.hl7_orm_port
        if settings.hl7_orm_auto_sync is not None:
            cfg["auto_sync"] = settings.hl7_orm_auto_sync
    return cfg


def save_hl7_config(payload: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(payload.get("enabled", True))
    listen_host = str(payload.get("listen_host", "0.0.0.0")).strip() or "0.0.0.0"
    listen_port = int(payload.get("listen_port", 2575))
    auto_sync = bool(payload.get("auto_sync", True))
    map_modality = bool(payload.get("map_modality_to_station", True))
    default_station = str(payload.get("default_station_aet", "")).strip().upper()[:16]
    sending_app = str(payload.get("sending_application", "LEXPACS")).strip()[:64] or "LEXPACS"
    sending_fac = str(payload.get("sending_facility", "LEX")).strip()[:64] or "LEX"

    if listen_port < 1 or listen_port > 65535:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Porta HL7 inválida.")

    data = _read_raw()
    stats = data.get("hl7_stats") or {}
    data["hl7_orm"] = {
        "enabled": enabled,
        "listen_host": listen_host,
        "listen_port": listen_port,
        "auto_sync": auto_sync,
        "map_modality_to_station": map_modality,
        "default_station_aet": default_station,
        "sending_application": sending_app,
        "sending_facility": sending_fac,
    }
    data["hl7_stats"] = stats
    _write_raw(data)
    return get_hl7_config()


def get_hl7_stats() -> dict[str, Any]:
    data = _read_raw()
    stats = dict(data.get("hl7_stats") or {})
    return {
        "messages_total": int(stats.get("messages_total") or 0),
        "last_at": str(stats.get("last_at") or ""),
        "last_accession": str(stats.get("last_accession") or ""),
        "last_control": str(stats.get("last_control") or ""),
        "last_message_type": str(stats.get("last_message_type") or ""),
        "last_error": str(stats.get("last_error") or ""),
    }


def record_hl7_message(
    *,
    accession: str = "",
    control: str = "",
    message_type: str = "",
    error: str = "",
) -> dict[str, Any]:
    from .mwl_sql import utc_now_iso

    data = _read_raw()
    stats = dict(data.get("hl7_stats") or {})
    stats["messages_total"] = int(stats.get("messages_total") or 0) + 1
    stats["last_at"] = utc_now_iso()
    if accession:
        stats["last_accession"] = accession[:32]
    if control:
        stats["last_control"] = control[:8]
    if message_type:
        stats["last_message_type"] = message_type[:32]
    stats["last_error"] = error[:240]
    data["hl7_stats"] = stats
    _write_raw(data)
    return get_hl7_stats()
