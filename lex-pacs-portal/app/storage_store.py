from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from .mwl_sql import _read_raw, _write_raw, _settings_path
from .pacs_config import INGEST_TRANSCODING_OPTIONS, validate_ingest_transcoding

DEFAULT_STORAGE = {
    "enabled": False,
    "run_interval_hours": 24,
    "batch_size": 5,
    "pause_seconds": 2,
    "rules": [],
    "status": "idle",
    "cursor": 0,
    "queue_total": 0,
    "stats": {
        "compressed": 0,
        "skipped": 0,
        "failed": 0,
        "instances": 0,
    },
    "last_run_at": "",
    "last_error": "",
    "started_at": "",
    "updated_at": "",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _queue_path() -> Path:
    return _settings_path().parent / "storage-queue.json"


def get_storage_config() -> dict[str, Any]:
    data = _read_raw()
    cfg = deepcopy(data.get("storage_policies") or DEFAULT_STORAGE)
    for key, value in DEFAULT_STORAGE.items():
        if key not in cfg:
            cfg[key] = deepcopy(value) if isinstance(value, dict) else value
    stats = cfg.setdefault("stats", {})
    for key, value in DEFAULT_STORAGE["stats"].items():
        stats.setdefault(key, value)
    rules = cfg.get("rules")
    if not isinstance(rules, list):
        cfg["rules"] = []
    return cfg


def save_storage_config(payload: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(payload.get("enabled", False))
    interval = int(payload.get("run_interval_hours", 24))
    batch_size = int(payload.get("batch_size", 5))
    pause_seconds = int(payload.get("pause_seconds", 2))
    raw_rules = payload.get("rules") or []

    if interval < 1 or interval > 168:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Intervalo de armazenamento inválido.")
    if batch_size < 1 or batch_size > 50:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tamanho do lote inválido.")
    if pause_seconds < 0 or pause_seconds > 300:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pausa entre exames inválida.")

    rules: list[dict[str, Any]] = []
    for item in raw_rules:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("id") or "").strip() or uuid.uuid4().hex[:12]
        min_age = int(item.get("min_age_years", 1))
        ts = validate_ingest_transcoding(str(item.get("transfer_syntax", "")).strip())
        if not ts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cada regra precisa de um transfer syntax de compressão.",
            )
        if min_age < 1 or min_age > 50:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idade mínima inválida.")
        modalities = [
            str(mod).strip().upper()[:16]
            for mod in (item.get("modalities") or [])
            if str(mod).strip()
        ]
        rules.append(
            {
                "id": rule_id,
                "enabled": bool(item.get("enabled", True)),
                "min_age_years": min_age,
                "transfer_syntax": ts,
                "modalities": modalities,
            }
        )

    data = _read_raw()
    current = deepcopy(data.get("storage_policies") or DEFAULT_STORAGE)
    current["enabled"] = enabled
    current["run_interval_hours"] = interval
    current["batch_size"] = batch_size
    current["pause_seconds"] = pause_seconds
    current["rules"] = rules
    current["updated_at"] = utc_now_iso()
    data["storage_policies"] = current
    _write_raw(data)
    return get_storage_config()


def update_storage_state(**fields: Any) -> dict[str, Any]:
    data = _read_raw()
    cfg = deepcopy(data.get("storage_policies") or DEFAULT_STORAGE)
    for key, value in fields.items():
        if key == "stats" and isinstance(value, dict):
            stats = cfg.setdefault("stats", deepcopy(DEFAULT_STORAGE["stats"]))
            stats.update(value)
        else:
            cfg[key] = value
    cfg["updated_at"] = utc_now_iso()
    data["storage_policies"] = cfg
    _write_raw(data)
    return cfg


def load_storage_queue() -> list[dict[str, Any]]:
    path = _queue_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_storage_queue(items: list[dict[str, Any]]) -> None:
    path = _queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_storage_queue() -> None:
    path = _queue_path()
    if path.is_file():
        path.unlink()


def storage_transfer_syntax_options() -> list[dict[str, str]]:
    return [
        {"uid": uid, "label": label}
        for uid, label in INGEST_TRANSCODING_OPTIONS.items()
        if uid
    ]


def get_storage_status() -> dict[str, Any]:
    cfg = get_storage_config()
    queue = load_storage_queue()
    cursor = int(cfg.get("cursor") or 0)
    total = len(queue) if queue else int(cfg.get("queue_total") or 0)
    pending = max(0, total - cursor)
    stats = cfg.get("stats") or {}
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "run_interval_hours": int(cfg.get("run_interval_hours") or 24),
        "batch_size": int(cfg.get("batch_size") or 5),
        "pause_seconds": int(cfg.get("pause_seconds") or 2),
        "rules": cfg.get("rules") or [],
        "status": str(cfg.get("status") or "idle"),
        "cursor": cursor,
        "queue_total": total,
        "pending": pending,
        "progress_percent": round((cursor / total) * 100, 1) if total else 0.0,
        "stats": stats,
        "last_run_at": str(cfg.get("last_run_at") or ""),
        "last_error": str(cfg.get("last_error") or ""),
        "started_at": str(cfg.get("started_at") or ""),
        "updated_at": str(cfg.get("updated_at") or ""),
        "transfer_syntax_options": storage_transfer_syntax_options(),
    }
