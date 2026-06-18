from __future__ import annotations

import asyncio
import logging
from typing import Any

from .audit import log_event
from .mwl_sql import get_mwl_sql_config, get_mwl_sync_meta, save_mwl_sync_meta, utc_now_iso
from .mwl_sync import sync_mwl_from_sql

logger = logging.getLogger("lex_pacs.mwl_scheduler")

_scheduler_task: asyncio.Task | None = None


def _seconds_since_last_sync(meta: dict[str, Any]) -> float | None:
    last_at = str(meta.get("last_at") or "").strip()
    if not last_at:
        return None
    from datetime import datetime, timezone

    try:
        parsed = datetime.fromisoformat(last_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - parsed).total_seconds()
    except ValueError:
        return None


def run_mwl_sync(actor: str = "manual") -> dict[str, Any]:
    cfg = get_mwl_sql_config()
    if not cfg.get("enabled", True):
        raise RuntimeError("Sync SQL MWL desabilitado.")
    try:
        result = sync_mwl_from_sql()
        save_mwl_sync_meta(
            last_at=utc_now_iso(),
            last_synced=result.get("synced", 0),
            last_actor=actor,
            last_error="",
        )
        return result
    except Exception as exc:
        save_mwl_sync_meta(last_error=str(exc)[:240])
        raise


async def _scheduler_loop() -> None:
    await asyncio.sleep(15)
    while True:
        try:
            cfg = get_mwl_sql_config()
            if cfg.get("enabled", True):
                interval_sec = max(60, int(cfg.get("sync_interval_minutes", 5)) * 60)
                meta = get_mwl_sync_meta()
                elapsed = _seconds_since_last_sync(meta)
                if elapsed is None or elapsed >= interval_sec:
                    result = await asyncio.to_thread(run_mwl_sync, "scheduler")
                    log_event(
                        "mwl_sync",
                        "scheduler",
                        synced=result.get("synced", 0),
                        auth_method="scheduler",
                    )
                    logger.info("MWL sync automático concluído")
        except Exception as exc:
            logger.warning("MWL sync automático falhou: %s", exc)
        await asyncio.sleep(60)


def start_mwl_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop())
