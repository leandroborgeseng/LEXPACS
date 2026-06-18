from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from .config import settings

DEFAULT_MWL_SQL = {
    "enabled": True,
    "host": "postgres",
    "port": 5432,
    "database": "orthanc",
    "username": "orthanc",
    "password_env": "POSTGRES_PASSWORD",
    "table": "lex_mwl_schedule",
    "sync_interval_minutes": 5,
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


def get_mwl_sql_config() -> dict[str, Any]:
    cfg = deepcopy(_read_raw()["mwl_sql"])
    password = ""
    env_name = str(cfg.get("password_env", "POSTGRES_PASSWORD"))
    import os

    password = os.environ.get(env_name, "")
    cfg["password_configured"] = bool(password)
    cfg.pop("password", None)
    return cfg


def save_mwl_sql_config(payload: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(payload.get("enabled", True))
    host = str(payload.get("host", "")).strip() or "postgres"
    port = int(payload.get("port", 5432))
    database = str(payload.get("database", "")).strip() or "orthanc"
    username = str(payload.get("username", "")).strip() or "orthanc"
    table = str(payload.get("table", "")).strip() or "lex_mwl_schedule"
    password_env = str(payload.get("password_env", "")).strip() or "POSTGRES_PASSWORD"
    sync_interval = int(payload.get("sync_interval_minutes", 5))

    if port < 1 or port > 65535:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Porta SQL inválida.")
    if not table.replace("_", "").isalnum():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nome de tabela inválido.")

    data = _read_raw()
    data["mwl_sql"] = {
        "enabled": enabled,
        "host": host,
        "port": port,
        "database": database,
        "username": username,
        "password_env": password_env,
        "table": table,
        "sync_interval_minutes": max(1, sync_interval),
    }
    _write_raw(data)
    return get_mwl_sql_config()


def mwl_sql_connection_params() -> dict[str, Any]:
    cfg = _read_raw()["mwl_sql"]
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
        "host": cfg.get("host", "postgres"),
        "port": int(cfg.get("port", 5432)),
        "database": cfg.get("database", "orthanc"),
        "user": cfg.get("username", "orthanc"),
        "password": password,
        "table": cfg.get("table", "lex_mwl_schedule"),
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
