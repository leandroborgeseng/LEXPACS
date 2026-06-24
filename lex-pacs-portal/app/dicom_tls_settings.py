from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException, status

from .mwl_sql import _read_raw, _write_raw, utc_now_iso

DEFAULT_DICOM_TLS = {
    "enabled": False,
    "remote_certificate_required": False,
    "smoke_consumer_aet": "LEXTLS",
    "min_protocol_version": 0,
}


def get_dicom_tls_config() -> dict[str, Any]:
    data = _read_raw()
    cfg = deepcopy(DEFAULT_DICOM_TLS)
    cfg.update(data.get("dicom_tls") or {})
    cfg["enabled"] = bool(cfg.get("enabled"))
    cfg["remote_certificate_required"] = bool(cfg.get("remote_certificate_required"))
    cfg["smoke_consumer_aet"] = (
        str(cfg.get("smoke_consumer_aet") or "LEXTLS").strip().upper()[:16] or "LEXTLS"
    )
    try:
        cfg["min_protocol_version"] = max(0, min(5, int(cfg.get("min_protocol_version") or 0)))
    except (TypeError, ValueError):
        cfg["min_protocol_version"] = 0
    return cfg


def save_dicom_tls_config(payload: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(payload.get("enabled"))
    remote_required = bool(payload.get("remote_certificate_required"))
    aet = str(payload.get("smoke_consumer_aet", "LEXTLS")).strip().upper()[:16] or "LEXTLS"
    try:
        min_proto = max(0, min(5, int(payload.get("min_protocol_version", 0))))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Versão mínima TLS inválida (0–5).",
        ) from None

    data = _read_raw()
    stats = data.get("dicom_tls_stats") or {}
    data["dicom_tls"] = {
        "enabled": enabled,
        "remote_certificate_required": remote_required,
        "smoke_consumer_aet": aet,
        "min_protocol_version": min_proto,
    }
    data["dicom_tls_stats"] = stats
    _write_raw(data)
    return get_dicom_tls_config()


def get_dicom_tls_stats() -> dict[str, Any]:
    data = _read_raw()
    stats = dict(data.get("dicom_tls_stats") or {})
    return {
        "last_at": str(stats.get("last_at") or ""),
        "last_actor": str(stats.get("last_actor") or ""),
        "last_success": bool(stats.get("last_success")),
        "last_error": str(stats.get("last_error") or ""),
        "generated_at": str(stats.get("generated_at") or ""),
        "generated_by": str(stats.get("generated_by") or ""),
    }


def record_dicom_tls_test(*, actor: str, success: bool, error: str = "") -> dict[str, Any]:
    data = _read_raw()
    data["dicom_tls_stats"] = {
        **dict(data.get("dicom_tls_stats") or {}),
        "last_at": utc_now_iso(),
        "last_actor": actor,
        "last_success": success,
        "last_error": error[:240],
    }
    _write_raw(data)
    return get_dicom_tls_stats()


def record_dicom_tls_generated(*, actor: str) -> dict[str, Any]:
    data = _read_raw()
    data["dicom_tls_stats"] = {
        **dict(data.get("dicom_tls_stats") or {}),
        "generated_at": utc_now_iso(),
        "generated_by": actor,
    }
    _write_raw(data)
    return get_dicom_tls_stats()
