from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status

from .config import settings
from .mwl_drivers import (
    DEFAULT_CUSTOM_SQL,
    DEFAULT_FIELD_MAPPING,
    default_port,
    list_drivers,
)

DEFAULT_MWL_SQL = {
    "enabled": True,
    "driver": "postgresql",
    "mode": "table",
    "host": "database",
    "port": 5432,
    "database": "orthanc",
    "username": "orthanc",
    "password_env": "POSTGRES_PASSWORD",
    "table": "lex_mwl_schedule",
    "custom_sql": DEFAULT_CUSTOM_SQL,
    "field_mapping": deepcopy(DEFAULT_FIELD_MAPPING),
    "modality_filter": [],
    "modality_routes": [],
    "sync_interval_minutes": 5,
    # Hoje e amanhã. O fuso padrão é o do hospital (Brasil); os dois são configuráveis.
    "schedule_window_days": 2,
    "schedule_timezone": "America/Sao_Paulo",
    "login_timeout_seconds": 30,
    "query_timeout_seconds": 120,
}


def _settings_path() -> Path:
    return Path(settings.orthanc_config_path).parent / "lex-pacs-settings.json"


def _read_raw() -> dict:
    path = _settings_path()
    if not path.is_file():
        return {"equipment": [], "worklist_views": [], "mwl_sql": deepcopy(DEFAULT_MWL_SQL)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível ler as configurações MWL.",
        ) from exc
    if "mwl_sql" not in data:
        data["mwl_sql"] = deepcopy(DEFAULT_MWL_SQL)
    mwl = data.get("mwl_sql") or {}
    if mwl.get("host") == "postgres":
        mwl["host"] = "database"
        data["mwl_sql"] = mwl
        try:
            _write_raw(data)
        except HTTPException:
            pass
    return data


def _write_raw(data: dict) -> None:
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível salvar as configurações MWL.",
        ) from exc


def _bounded_int(value: Any, default: int, upper: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < 1:
        return default
    return min(number, upper)


def _timezone_name(value: Any, *, strict: bool) -> str:
    name = str(value or "").strip() or "America/Sao_Paulo"
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        if strict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fuso horário da janela MWL inválido.",
            )
        return "America/Sao_Paulo"
    return name


def _normalize_config(cfg: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(DEFAULT_MWL_SQL)
    out.update(cfg)
    driver = str(out.get("driver") or "postgresql")
    out["driver"] = driver
    out["mode"] = str(out.get("mode") or "table")
    out["port"] = int(out.get("port") or default_port(driver))
    out["field_mapping"] = dict(DEFAULT_FIELD_MAPPING)
    raw_map = cfg.get("field_mapping") or {}
    for key, value in raw_map.items():
        if key in DEFAULT_FIELD_MAPPING and str(value).strip():
            out["field_mapping"][key] = str(value).strip()
    routes = []
    for item in out.get("modality_routes") or []:
        mod = str(item.get("modality") or "").strip().upper()
        station = str(item.get("station_aet") or "").strip().upper()
        if mod:
            routes.append({"modality": mod, "station_aet": station})
    out["modality_routes"] = routes
    out["modality_filter"] = [
        str(m).strip().upper()
        for m in (out.get("modality_filter") or [])
        if str(m).strip()
    ]
    out["schedule_window_days"] = _bounded_int(out.get("schedule_window_days"), 2, 31)
    out["schedule_timezone"] = _timezone_name(out.get("schedule_timezone"), strict=False)
    out["login_timeout_seconds"] = _bounded_int(out.get("login_timeout_seconds"), 30, 120)
    out["query_timeout_seconds"] = _bounded_int(out.get("query_timeout_seconds"), 120, 600)
    out["sync_interval_minutes"] = _bounded_int(out.get("sync_interval_minutes"), 5, 1440)
    return out


def get_mwl_sql_config() -> dict[str, Any]:
    cfg = _normalize_config(_read_raw()["mwl_sql"])
    import os

    env_name = str(cfg.get("password_env", "POSTGRES_PASSWORD"))
    cfg["password_configured"] = bool(os.environ.get(env_name, ""))
    cfg["available_drivers"] = list_drivers()
    cfg.pop("password", None)
    return cfg


def save_mwl_sql_config(payload: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(payload.get("enabled", True))
    driver = str(payload.get("driver") or "postgresql").strip().lower()
    mode = str(payload.get("mode") or "table").strip().lower()
    host = str(payload.get("host", "")).strip() or "database"
    port = int(payload.get("port") or default_port(driver))
    database = str(payload.get("database", "")).strip()
    username = str(payload.get("username", "")).strip()
    table = str(payload.get("table", "")).strip() or "lex_mwl_schedule"
    password_env = str(payload.get("password_env", "")).strip() or "POSTGRES_PASSWORD"
    sync_interval = int(payload.get("sync_interval_minutes", 5))
    custom_sql = str(payload.get("custom_sql") or "").strip() or DEFAULT_CUSTOM_SQL
    try:
        window_days = int(payload.get("schedule_window_days") or 2)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Janela de agendados inválida.",
        ) from exc
    if window_days < 1 or window_days > 31:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Janela de agendados inválida.",
        )
    schedule_timezone = _timezone_name(payload.get("schedule_timezone"), strict=True)
    login_timeout = _bounded_int(payload.get("login_timeout_seconds"), 30, 120)
    query_timeout = _bounded_int(payload.get("query_timeout_seconds"), 120, 600)

    if driver not in {item["id"] for item in list_drivers()}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Driver SQL inválido.")
    if mode not in {"table", "custom"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Modo SQL inválido.")
    if port < 1 or port > 65535:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Porta SQL inválida.")
    if mode == "table" and not table.replace("_", "").isalnum():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nome de tabela inválido.")

    data = _read_raw()
    data["mwl_sql"] = _normalize_config(
        {
            "enabled": enabled,
            "driver": driver,
            "mode": mode,
            "host": host,
            "port": port,
            "database": database,
            "username": username,
            "password_env": password_env,
            "table": table,
            "custom_sql": custom_sql,
            "field_mapping": payload.get("field_mapping") or DEFAULT_FIELD_MAPPING,
            "modality_filter": payload.get("modality_filter") or [],
            "modality_routes": payload.get("modality_routes") or [],
            "sync_interval_minutes": max(1, sync_interval),
            "schedule_window_days": window_days,
            "schedule_timezone": schedule_timezone,
            "login_timeout_seconds": login_timeout,
            "query_timeout_seconds": query_timeout,
        }
    )
    _write_raw(data)
    return get_mwl_sql_config()


def postgres_connection_params() -> dict[str, Any]:
    """Parâmetros somente para psycopg2 (modo tabela interna PostgreSQL)."""
    raw = mwl_sql_connection_params()
    return {
        "host": raw["host"],
        "port": int(raw["port"]),
        "database": raw["database"],
        "user": raw.get("user") or raw.get("username", "orthanc"),
        "password": raw["password"],
        "table": raw["table"],
    }


def mwl_sql_connection_params() -> dict[str, Any]:
    cfg = _normalize_config(_read_raw()["mwl_sql"])
    if not cfg.get("enabled", True):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sync SQL MWL desabilitado.")
    import os

    env_name = str(cfg.get("password_env", "POSTGRES_PASSWORD"))
    password = os.environ.get(env_name, "")
    if not password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Senha SQL não configurada (env {env_name}).",
        )
    return {
        "driver": cfg.get("driver", "postgresql"),
        "host": cfg.get("host", "database"),
        "port": int(cfg.get("port", 5432)),
        "database": cfg.get("database", "orthanc"),
        "username": cfg.get("username", "orthanc"),
        "user": cfg.get("username", "orthanc"),
        "password": password,
        "password_env": env_name,
        "table": cfg.get("table", "lex_mwl_schedule"),
        "mode": cfg.get("mode", "table"),
        "custom_sql": cfg.get("custom_sql", ""),
        "field_mapping": cfg.get("field_mapping", DEFAULT_FIELD_MAPPING),
        "modality_filter": cfg.get("modality_filter", []),
        "modality_routes": cfg.get("modality_routes", []),
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _meta_count(meta: dict[str, Any], key: str, fallback_key: str | None = None) -> int:
    if key in meta and meta.get(key) is not None:
        return int(meta.get(key) or 0)
    if fallback_key is not None:
        return int(meta.get(fallback_key) or 0)
    return 0


def get_mwl_sync_meta() -> dict[str, Any]:
    data = _read_raw()
    meta = data.get("mwl_sync", {})
    return {
        "last_at": str(meta.get("last_at") or ""),
        "last_synced": int(meta.get("last_synced") or 0),
        "last_read": _meta_count(meta, "last_read", "last_synced"),
        "last_written": _meta_count(meta, "last_written", "last_synced"),
        "last_removed": _meta_count(meta, "last_removed"),
        "last_errors": _meta_count(meta, "last_errors"),
        "last_actor": str(meta.get("last_actor") or ""),
        "last_error": str(meta.get("last_error") or ""),
    }


def save_mwl_sync_meta(
    *,
    last_at: str | None = None,
    last_synced: int | None = None,
    last_read: int | None = None,
    last_written: int | None = None,
    last_removed: int | None = None,
    last_errors: int | None = None,
    last_actor: str | None = None,
    last_error: str | None = None,
) -> dict[str, Any]:
    data = _read_raw()
    meta = dict(data.get("mwl_sync", {}))
    updates = {
        "last_at": last_at,
        "last_synced": last_synced,
        "last_read": last_read,
        "last_written": last_written,
        "last_removed": last_removed,
        "last_errors": last_errors,
        "last_actor": last_actor,
        "last_error": last_error,
    }
    for key, value in updates.items():
        if value is not None:
            meta[key] = value
    data["mwl_sync"] = meta
    _write_raw(data)
    return get_mwl_sync_meta()
