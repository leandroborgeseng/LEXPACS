from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException, status

from .mwl_sql import _read_raw, _write_raw, utc_now_iso

DEFAULT_QR = {
    "query_retrieve_size": 100,
    "smoke_consumer_aet": "LEXQR",
    "smoke_consumer_host": "portal",
}


def get_qr_config() -> dict[str, Any]:
    data = _read_raw()
    cfg = deepcopy(DEFAULT_QR)
    cfg.update(data.get("query_retrieve") or {})
    cfg["query_retrieve_size"] = max(10, min(1000, int(cfg.get("query_retrieve_size") or 100)))
    cfg["smoke_consumer_aet"] = str(cfg.get("smoke_consumer_aet") or "LEXQR").strip().upper()[:16]
    cfg["smoke_consumer_host"] = str(cfg.get("smoke_consumer_host") or "portal").strip()[:128]
    return cfg


def save_qr_config(payload: dict[str, Any]) -> dict[str, Any]:
    size = int(payload.get("query_retrieve_size", 100))
    aet = str(payload.get("smoke_consumer_aet", "LEXQR")).strip().upper()[:16] or "LEXQR"
    host = str(payload.get("smoke_consumer_host", "portal")).strip()[:128] or "portal"
    if size < 10 or size > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="QueryRetrieveSize deve estar entre 10 e 1000.",
        )
    data = _read_raw()
    stats = data.get("qr_stats") or {}
    data["query_retrieve"] = {
        "query_retrieve_size": size,
        "smoke_consumer_aet": aet,
        "smoke_consumer_host": host,
    }
    data["qr_stats"] = stats
    _write_raw(data)
    return get_qr_config()


def get_qr_stats() -> dict[str, Any]:
    data = _read_raw()
    stats = dict(data.get("qr_stats") or {})
    return {
        "last_at": str(stats.get("last_at") or ""),
        "last_actor": str(stats.get("last_actor") or ""),
        "last_find_count": int(stats.get("last_find_count") or 0),
        "last_error": str(stats.get("last_error") or ""),
        "last_success": bool(stats.get("last_success")),
    }


def record_qr_test(
    *,
    actor: str,
    find_count: int,
    success: bool,
    error: str = "",
) -> dict[str, Any]:
    data = _read_raw()
    data["qr_stats"] = {
        "last_at": utc_now_iso(),
        "last_actor": actor,
        "last_find_count": find_count,
        "last_success": success,
        "last_error": error[:240],
    }
    _write_raw(data)
    return get_qr_stats()
