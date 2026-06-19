from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import settings


def _retention_fields() -> dict[str, int]:
    return {
        "retention_days": settings.backup_retention_days,
        "retention_daily": settings.backup_retention_daily,
        "retention_weekly": settings.backup_retention_weekly,
        "interval_hours": settings.backup_interval_hours,
    }


def get_backup_status() -> dict[str, Any]:
    base = _retention_fields()
    path = Path(settings.backup_status_path)
    if not path.is_file():
        return {
            "configured": False,
            "success": False,
            "last_at": "",
            "last_path": "",
            "lex_pacs_version": "",
            "backup_root": "",
            **base,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "configured": True,
            "success": False,
            "last_at": "",
            "last_path": "",
            "lex_pacs_version": "",
            "backup_root": "",
            **base,
            "error": "Não foi possível ler latest-status.json",
        }
    return {
        "configured": True,
        "success": bool(data.get("success")),
        "last_at": str(data.get("last_at") or ""),
        "last_path": str(data.get("last_path") or ""),
        "lex_pacs_version": str(data.get("lex_pacs_version") or ""),
        "backup_root": str(data.get("backup_root") or ""),
        **base,
    }
