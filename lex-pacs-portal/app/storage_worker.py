from __future__ import annotations

import asyncio
import logging

from .storage_service import maybe_start_scheduled_run, process_storage_batch
from .storage_store import get_storage_config

logger = logging.getLogger("lex_pacs.storage_worker")

_worker_task: asyncio.Task | None = None
_kick_event: asyncio.Event | None = None


def kick_storage_worker() -> None:
    global _kick_event
    if _kick_event is None:
        return
    _kick_event.set()


async def _worker_loop() -> None:
    global _kick_event
    _kick_event = asyncio.Event()
    await asyncio.sleep(15)
    while True:
        try:
            maybe_start_scheduled_run()
            cfg = get_storage_config()
            status = str(cfg.get("status") or "idle")
            if status == "running":
                result = await asyncio.to_thread(process_storage_batch)
                pause_seconds = max(0, int(cfg.get("pause_seconds") or 2))
                if result.get("processed", 0) > 0 and pause_seconds:
                    await asyncio.sleep(pause_seconds)
                elif result.get("status") == "completed":
                    logger.info("Política de armazenamento concluída")
                    await asyncio.sleep(5)
                else:
                    await asyncio.sleep(1)
            else:
                try:
                    await asyncio.wait_for(_kick_event.wait(), timeout=60.0)
                    _kick_event.clear()
                except asyncio.TimeoutError:
                    continue
        except Exception as exc:
            logger.warning("Storage worker: erro — %s", exc)
            await asyncio.sleep(10)


def start_storage_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_worker_loop())
