from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from .config import settings
from .mwl_sql import _read_raw, _write_raw, _settings_path

DEFAULT_PORTAL_OPS = {
    "backup_interval_hours": 24,
    "backup_retention_daily": 7,
    "backup_retention_weekly": 4,
    "backup_retention_days": 14,
    "login_rate_limit_attempts": 20,
    "login_rate_limit_window_seconds": 60,
}


def _env_defaults() -> dict[str, int]:
    return {
        "backup_interval_hours": settings.backup_interval_hours,
        "backup_retention_daily": settings.backup_retention_daily,
        "backup_retention_weekly": settings.backup_retention_weekly,
        "backup_retention_days": settings.backup_retention_days,
        "login_rate_limit_attempts": settings.login_rate_limit_attempts,
        "login_rate_limit_window_seconds": settings.login_rate_limit_window_seconds,
    }


def get_portal_ops() -> dict[str, Any]:
    data = _read_raw()
    cfg = deepcopy(data.get("portal_ops") or DEFAULT_PORTAL_OPS)
    env = _env_defaults()
    for key, value in DEFAULT_PORTAL_OPS.items():
        if key not in cfg:
            cfg[key] = env.get(key, value)
    return cfg


def save_portal_ops(payload: dict[str, Any]) -> dict[str, Any]:
    interval = int(payload.get("backup_interval_hours", 24))
    daily = int(payload.get("backup_retention_daily", 7))
    weekly = int(payload.get("backup_retention_weekly", 4))
    days = int(payload.get("backup_retention_days", 14))
    attempts = int(payload.get("login_rate_limit_attempts", 20))
    window = int(payload.get("login_rate_limit_window_seconds", 60))

    if interval < 1 or interval > 168:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Intervalo de backup inválido.")
    if daily < 1 or weekly < 1 or days < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Retenção de backup inválida.")
    if attempts < 1 or window < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rate limit inválido.")

    data = _read_raw()
    data["portal_ops"] = {
        "backup_interval_hours": interval,
        "backup_retention_daily": daily,
        "backup_retention_weekly": weekly,
        "backup_retention_days": days,
        "login_rate_limit_attempts": attempts,
        "login_rate_limit_window_seconds": window,
    }
    _write_raw(data)
    _write_ops_env(data["portal_ops"])
    return get_portal_ops()


def _write_ops_env(ops: dict[str, int]) -> None:
    path = _settings_path().parent / "portal-ops.env"
    lines = [
        f"BACKUP_INTERVAL_HOURS={ops['backup_interval_hours']}",
        f"BACKUP_RETENTION_DAILY={ops['backup_retention_daily']}",
        f"BACKUP_RETENTION_WEEKLY={ops['backup_retention_weekly']}",
        f"BACKUP_RETENTION_DAYS={ops['backup_retention_days']}",
        f"LOGIN_RATE_LIMIT_ATTEMPTS={ops['login_rate_limit_attempts']}",
        f"LOGIN_RATE_LIMIT_WINDOW_SECONDS={ops['login_rate_limit_window_seconds']}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_portal_ops_env() -> None:
    env_path = _settings_path().parent / "portal-ops.env"
    if env_path.is_file():
        return
    _write_ops_env(get_portal_ops())


def get_login_rate_limit() -> tuple[int, int]:
    ops = get_portal_ops()
    return int(ops["login_rate_limit_attempts"]), int(ops["login_rate_limit_window_seconds"])


def get_backup_policy() -> dict[str, int]:
    ops = get_portal_ops()
    return {
        "retention_days": int(ops["backup_retention_days"]),
        "retention_daily": int(ops["backup_retention_daily"]),
        "retention_weekly": int(ops["backup_retention_weekly"]),
        "interval_hours": int(ops["backup_interval_hours"]),
    }
