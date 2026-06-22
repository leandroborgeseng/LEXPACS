from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from .config import settings
from .lex_settings import get_equipment
from .migration_orthanc import (
    MigrationOrthancError,
    discover_remote_studies,
    modality_echo,
    retrieve_remote_study,
    study_exists_locally,
)
from .migration_store import (
    MIGRATION_MODALITY_KEY,
    clear_migration_queue,
    get_migration_config,
    get_migration_source_for_orthanc,
    load_migration_queue,
    save_migration_config,
    save_migration_queue,
    update_migration_state,
    utc_now_iso,
)


def _orthanc_config_path() -> Path:
    return Path(settings.orthanc_config_path)


def _read_orthanc_config() -> dict:
    path = _orthanc_config_path()
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="orthanc.json não encontrado.",
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _write_orthanc_config(config: dict) -> None:
    path = _orthanc_config_path()
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _build_equipment_modalities(equipment: list[dict]) -> dict[str, dict]:
    import re

    modalities: dict[str, dict] = {}
    for item in equipment:
        key = re.sub(r"[^A-Za-z0-9_]", "_", item["aet"])[:32] or "DEVICE"
        suffix = 1
        base = key
        while key in modalities and modalities[key]["AET"] != item["aet"]:
            key = f"{base}_{suffix}"
            suffix += 1
        modalities[key] = {
            "AET": item["aet"],
            "Host": item["host"],
            "Port": item["port"],
            "AllowStore": True,
            "AllowEcho": True,
            "AllowFind": True,
            "AllowMove": True,
        }
    return modalities


def sync_migration_modality_to_orthanc() -> bool:
    config = _read_orthanc_config()
    modalities = _build_equipment_modalities(get_equipment())
    mig = get_migration_source_for_orthanc()
    if mig:
        modalities[MIGRATION_MODALITY_KEY] = mig
    else:
        modalities.pop(MIGRATION_MODALITY_KEY, None)
    previous = config.get("DicomModalities") or {}
    if previous == modalities:
        return False
    config["DicomModalities"] = modalities
    _write_orthanc_config(config)
    return True


def save_migration_settings(payload: dict[str, Any]) -> dict[str, Any]:
    saved = save_migration_config(payload)
    sync_migration_modality_to_orthanc()
    return saved


def test_migration_echo() -> dict[str, Any]:
    cfg = get_migration_config()
    src = cfg.get("source") or {}
    if not str(src.get("aet") or "").strip() or not str(src.get("host") or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Configure o PACS de origem.")
    sync_migration_modality_to_orthanc()
    try:
        result = modality_echo()
    except MigrationOrthancError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"ok": True, "result": result}


def run_migration_discovery() -> dict[str, Any]:
    cfg = get_migration_config()
    status_value = str(cfg.get("status") or "idle")
    if status_value == "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pause a migração antes de redescobrir.")

    sync_migration_modality_to_orthanc()
    update_migration_state(status="discovering", last_error="")
    try:
        studies = discover_remote_studies(cfg.get("filters") or {})
    except MigrationOrthancError as exc:
        update_migration_state(status="error", last_error=str(exc)[:240])
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    save_migration_queue(studies)
    update_migration_state(
        status="idle",
        cursor=0,
        queue_total=len(studies),
        discovered_at=utc_now_iso(),
        stats=deepcopy({"completed": 0, "failed": 0, "skipped": 0, "instances_imported": 0}),
        last_error="",
    )
    return {
        "discovered": len(studies),
        "queue_total": len(studies),
    }


def start_migration() -> dict[str, Any]:
    cfg = get_migration_config()
    status_value = str(cfg.get("status") or "idle")
    queue = load_migration_queue()
    if not queue:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum estudo na fila. Execute a descoberta primeiro.",
        )
    if status_value == "running":
        return {"status": "running", "message": "Migração já em execução."}
    if status_value == "completed" and int(cfg.get("cursor") or 0) >= len(queue):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Migração já concluída.")

    fields: dict[str, Any] = {"status": "running", "last_error": ""}
    if not cfg.get("started_at"):
        fields["started_at"] = utc_now_iso()
    update_migration_state(**fields)
    from .migration_worker import kick_migration_worker

    kick_migration_worker()
    return {"status": "running", "pending": max(0, len(queue) - int(cfg.get("cursor") or 0))}


def pause_migration() -> dict[str, Any]:
    cfg = get_migration_config()
    if str(cfg.get("status") or "") != "running":
        return {"status": cfg.get("status"), "message": "Migração não estava em execução."}
    update_migration_state(status="paused")
    return {"status": "paused"}


def reset_migration(clear_queue: bool = True) -> dict[str, Any]:
    cfg = get_migration_config()
    if str(cfg.get("status") or "") == "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pause a migração antes de resetar.")
    if clear_queue:
        clear_migration_queue()
    update_migration_state(
        status="idle",
        cursor=0,
        queue_total=0,
        last_error="",
        started_at="",
        discovered_at="",
        last_study_uid="",
        stats={"completed": 0, "failed": 0, "skipped": 0, "instances_imported": 0},
    )
    return {"status": "idle"}


def process_migration_batch() -> dict[str, Any]:
    cfg = get_migration_config()
    if str(cfg.get("status") or "") != "running":
        return {"processed": 0, "status": cfg.get("status")}

    queue = load_migration_queue()
    cursor = int(cfg.get("cursor") or 0)
    if cursor >= len(queue):
        update_migration_state(status="completed")
        return {"processed": 0, "status": "completed"}

    batch_size = max(1, int(cfg.get("batch_size") or 1))
    skip_existing = bool(cfg.get("skip_existing", True))
    stats = dict(cfg.get("stats") or {})
    processed = 0
    last_error = ""

    for _ in range(batch_size):
        cfg = get_migration_config()
        if str(cfg.get("status") or "") != "running":
            break
        queue = load_migration_queue()
        cursor = int(cfg.get("cursor") or 0)
        if cursor >= len(queue):
            update_migration_state(status="completed")
            break

        item = queue[cursor]
        study_uid = str(item.get("study_instance_uid") or "")
        try:
            if skip_existing and study_exists_locally(study_uid):
                stats["skipped"] = int(stats.get("skipped") or 0) + 1
            else:
                imported = retrieve_remote_study(study_uid)
                stats["instances_imported"] = int(stats.get("instances_imported") or 0) + imported
                stats["completed"] = int(stats.get("completed") or 0) + 1
        except MigrationOrthancError as exc:
            stats["failed"] = int(stats.get("failed") or 0) + 1
            last_error = str(exc)[:240]
        except Exception as exc:
            stats["failed"] = int(stats.get("failed") or 0) + 1
            last_error = str(exc)[:240]

        cursor += 1
        update_migration_state(
            cursor=cursor,
            stats=stats,
            last_study_uid=study_uid,
            last_error=last_error,
            status="completed" if cursor >= len(queue) else "running",
        )
        processed += 1

    return {
        "processed": processed,
        "status": get_migration_config().get("status"),
        "cursor": int(get_migration_config().get("cursor") or 0),
        "stats": get_migration_config().get("stats") or {},
    }
