from __future__ import annotations

import asyncio
import logging

from .migration_service import process_migration_batch
from .migration_store import get_migration_config

logger = logging.getLogger("lex_pacs.migration_worker")

_worker_task: asyncio.Task | None = None
_kick_event: asyncio.Event | None = None


def kick_migration_worker() -> None:
    global _kick_event
    if _kick_event is None:
        return
    _kick_event.set()


async def _worker_loop() -> None:
    global _kick_event
    _kick_event = asyncio.Event()
    await asyncio.sleep(10)
    while True:
        try:
            cfg = get_migration_config()
            status = str(cfg.get("status") or "idle")
            if status == "running":
                result = await asyncio.to_thread(process_migration_batch)
                pause_seconds = max(0, int(cfg.get("pause_seconds") or 2))
                if result.get("processed", 0) > 0 and pause_seconds:
                    await asyncio.sleep(pause_seconds)
                elif result.get("status") == "completed":
                    logger.info("Migração PACS concluída")
                else:
                    await asyncio.sleep(1)
            else:
                await _kick_event.wait()
                _kick_event.clear()
        except Exception as exc:
            logger.warning("Migração PACS: erro no worker — %s", exc)
            await asyncio.sleep(5)


def start_migration_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_worker_loop())
