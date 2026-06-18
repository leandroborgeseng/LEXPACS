from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings

AUDIT_FILE = Path(settings.audit_data_path) / "audit.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_dir() -> None:
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)


def log_event(event_type: str, actor: str, **details: Any) -> dict[str, Any]:
    entry = {
        "timestamp": _utc_now(),
        "event": event_type,
        "actor": actor or "unknown",
        **{key: value for key, value in details.items() if value is not None},
    }
    _ensure_dir()
    with AUDIT_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def list_events(*, limit: int = 100, event_type: str = "") -> list[dict[str, Any]]:
    if not AUDIT_FILE.is_file():
        return []
    lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event_type and item.get("event") != event_type:
            continue
        events.append(item)
        if len(events) >= limit:
            break
    return events
