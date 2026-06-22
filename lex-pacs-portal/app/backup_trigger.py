from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .mwl_sql import _settings_path


def request_backup() -> None:
    path = _settings_path().parent / "backup-trigger"
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    path.write_text(stamp + "\n", encoding="utf-8")


def clear_backup_trigger() -> None:
    path = _settings_path().parent / "backup-trigger"
    if path.is_file():
        path.unlink(missing_ok=True)
