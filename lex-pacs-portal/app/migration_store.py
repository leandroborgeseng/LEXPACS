from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from .config import settings
from .mwl_sql import _read_raw, _write_raw, _settings_path

MIGRATION_MODALITY_KEY = "LEX_MIG_SRC"

DEFAULT_MIGRATION = {
    "source": {
        "label": "",
        "aet": "",
        "host": "",
        "port": 104,
    },
    "filters": {
        "study_date_from": "",
        "study_date_to": "",
        "patient_id": "",
        "modality": "",
    },
    "batch_size": 1,
    "pause_seconds": 2,
    "skip_existing": True,
    "status": "idle",
    "cursor": 0,
    "queue_total": 0,
    "stats": {
        "completed": 0,
        "failed": 0,
        "skipped": 0,
        "instances_imported": 0,
    },
    "last_error": "",
    "started_at": "",
    "updated_at": "",
    "last_study_uid": "",
    "discovered_at": "",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _queue_path() -> Path:
    return _settings_path().parent / "migration-queue.json"


def get_migration_config() -> dict[str, Any]:
    data = _read_raw()
    cfg = deepcopy(data.get("pacs_migration") or DEFAULT_MIGRATION)
    for key, value in DEFAULT_MIGRATION.items():
        if key not in cfg:
            cfg[key] = deepcopy(value) if isinstance(value, dict) else value
    src = cfg.setdefault("source", {})
    for key, value in DEFAULT_MIGRATION["source"].items():
        src.setdefault(key, value)
    flt = cfg.setdefault("filters", {})
    for key, value in DEFAULT_MIGRATION["filters"].items():
        flt.setdefault(key, value)
    stats = cfg.setdefault("stats", {})
    for key, value in DEFAULT_MIGRATION["stats"].items():
        stats.setdefault(key, value)
    return cfg


def save_migration_config(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("source") or {}
    filters = payload.get("filters") or {}
    aet = str(source.get("aet", "")).strip().upper()[:16]
    host = str(source.get("host", "")).strip()[:128]
    port = int(source.get("port", 104))
    label = str(source.get("label", "")).strip()[:64]
    batch_size = max(1, min(int(payload.get("batch_size", 1)), 10))
    pause_seconds = max(0, min(int(payload.get("pause_seconds", 2)), 300))
    skip_existing = bool(payload.get("skip_existing", True))

    if aet and (not host or port < 1 or port > 65535):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Host/porta do PACS origem inválidos.")

    data = _read_raw()
    current = deepcopy(data.get("pacs_migration") or DEFAULT_MIGRATION)
    current["source"] = {
        "label": label,
        "aet": aet,
        "host": host,
        "port": port,
    }
    current["filters"] = {
        "study_date_from": str(filters.get("study_date_from", "")).strip()[:8],
        "study_date_to": str(filters.get("study_date_to", "")).strip()[:8],
        "patient_id": str(filters.get("patient_id", "")).strip()[:64],
        "modality": str(filters.get("modality", "")).strip().upper()[:16],
    }
    current["batch_size"] = batch_size
    current["pause_seconds"] = pause_seconds
    current["skip_existing"] = skip_existing
    current["updated_at"] = utc_now_iso()
    data["pacs_migration"] = current
    _write_raw(data)
    return get_migration_config()


def get_migration_source_for_orthanc() -> dict[str, Any] | None:
    cfg = get_migration_config()
    src = cfg.get("source") or {}
    aet = str(src.get("aet", "")).strip()
    host = str(src.get("host", "")).strip()
    if not aet or not host:
        return None
    return {
        "AET": aet,
        "Host": host,
        "Port": int(src.get("port", 104)),
        "AllowStore": True,
        "AllowEcho": True,
        "AllowFind": True,
        "AllowMove": True,
    }


def update_migration_state(**fields: Any) -> dict[str, Any]:
    data = _read_raw()
    cfg = deepcopy(data.get("pacs_migration") or DEFAULT_MIGRATION)
    for key, value in fields.items():
        if key == "stats" and isinstance(value, dict):
            stats = cfg.setdefault("stats", deepcopy(DEFAULT_MIGRATION["stats"]))
            stats.update(value)
        else:
            cfg[key] = value
    cfg["updated_at"] = utc_now_iso()
    data["pacs_migration"] = cfg
    _write_raw(data)
    return cfg


def load_migration_queue() -> list[dict[str, Any]]:
    path = _queue_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return data


def save_migration_queue(items: list[dict[str, Any]]) -> None:
    path = _queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_migration_queue() -> None:
    path = _queue_path()
    if path.is_file():
        path.unlink()


def get_migration_status() -> dict[str, Any]:
    cfg = get_migration_config()
    queue = load_migration_queue()
    cursor = int(cfg.get("cursor") or 0)
    total = len(queue) if queue else int(cfg.get("queue_total") or 0)
    pending = max(0, total - cursor)
    stats = cfg.get("stats") or {}
    return {
        "config": {
            "source": cfg.get("source") or {},
            "filters": cfg.get("filters") or {},
            "batch_size": int(cfg.get("batch_size") or 1),
            "pause_seconds": int(cfg.get("pause_seconds") or 2),
            "skip_existing": bool(cfg.get("skip_existing", True)),
        },
        "status": str(cfg.get("status") or "idle"),
        "cursor": cursor,
        "queue_total": total,
        "pending": pending,
        "progress_percent": round((cursor / total) * 100, 1) if total else 0.0,
        "stats": stats,
        "last_error": str(cfg.get("last_error") or ""),
        "started_at": str(cfg.get("started_at") or ""),
        "updated_at": str(cfg.get("updated_at") or ""),
        "last_study_uid": str(cfg.get("last_study_uid") or ""),
        "discovered_at": str(cfg.get("discovered_at") or ""),
        "modality_key": MIGRATION_MODALITY_KEY,
    }
