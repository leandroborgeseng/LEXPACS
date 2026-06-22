from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import httpx

from .config import settings
from .storage_store import (
    clear_storage_queue,
    get_storage_config,
    load_storage_queue,
    save_storage_queue,
    update_storage_state,
    utc_now_iso,
)

logger = logging.getLogger("lex_pacs.storage_service")


def _parse_dicom_date(value: str) -> date | None:
    raw = str(value or "").strip()
    if len(raw) < 8 or not raw[:8].isdigit():
        return None
    try:
        return datetime.strptime(raw[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _study_age_years(study_date: date | None, today: date) -> float | None:
    if study_date is None:
        return None
    return (today - study_date).days / 365.25


def _study_modalities(study: dict[str, Any]) -> set[str]:
    tags = study.get("MainDicomTags", {}) if isinstance(study, dict) else {}
    raw = str(tags.get("ModalitiesInStudy", "")).strip()
    if raw:
        return {part.strip().upper() for part in raw.split("\\") if part.strip()}
    modalities: set[str] = set()
    for series in study.get("Series", []) or []:
        if not isinstance(series, dict):
            continue
        modality = str(series.get("MainDicomTags", {}).get("Modality", "")).strip().upper()
        if modality:
            modalities.add(modality)
    return modalities


def _match_rule(study: dict[str, Any], rules: list[dict[str, Any]], today: date) -> dict[str, Any] | None:
    tags = study.get("MainDicomTags", {}) if isinstance(study, dict) else {}
    study_date = _parse_dicom_date(tags.get("StudyDate", ""))
    age_years = _study_age_years(study_date, today)
    if age_years is None:
        return None
    modalities = _study_modalities(study)
    matched: dict[str, Any] | None = None
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        min_age = int(rule.get("min_age_years") or 0)
        if age_years < min_age:
            continue
        rule_modalities = {str(m).upper() for m in (rule.get("modalities") or []) if str(m).strip()}
        if rule_modalities and not (modalities & rule_modalities):
            continue
        if matched is None or min_age > int(matched.get("min_age_years") or 0):
            matched = rule
    return matched


def _discover_queue_items() -> list[dict[str, Any]]:
    cfg = get_storage_config()
    rules = [rule for rule in (cfg.get("rules") or []) if rule.get("enabled", True)]
    if not rules:
        return []

    today = datetime.now(timezone.utc).date()
    items: list[dict[str, Any]] = []
    with httpx.Client(timeout=120.0) as client:
        base = settings.orthanc_url.rstrip("/")
        response = client.post(
            f"{base}/tools/find",
            json={"Level": "Study", "Query": {}, "Expand": True},
        )
        response.raise_for_status()
        studies = response.json()

    for study in studies:
        if not isinstance(study, dict):
            continue
        rule = _match_rule(study, rules, today)
        if not rule:
            continue
        study_id = str(study.get("ID", "")).strip()
        if not study_id:
            continue
        tags = study.get("MainDicomTags", {}) or {}
        items.append(
            {
                "study_id": study_id,
                "study_uid": str(tags.get("StudyInstanceUID", "")).strip(),
                "transfer_syntax": str(rule.get("transfer_syntax") or "").strip(),
                "min_age_years": int(rule.get("min_age_years") or 0),
            }
        )
    return items


def start_storage_run() -> dict[str, Any]:
    cfg = get_storage_config()
    if str(cfg.get("status") or "") == "running":
        return {"status": "running", "queue_total": int(cfg.get("queue_total") or 0)}

    queue = _discover_queue_items()
    save_storage_queue(queue)
    update_storage_state(
        status="running",
        cursor=0,
        queue_total=len(queue),
        stats={"compressed": 0, "skipped": 0, "failed": 0, "instances": 0},
        last_error="",
        started_at=utc_now_iso(),
    )
    return {"status": "running", "queue_total": len(queue)}


def pause_storage_run() -> dict[str, Any]:
    update_storage_state(status="paused")
    return {"status": "paused"}


def reset_storage_run() -> dict[str, Any]:
    clear_storage_queue()
    update_storage_state(
        status="idle",
        cursor=0,
        queue_total=0,
        last_error="",
        stats={"compressed": 0, "skipped": 0, "failed": 0, "instances": 0},
    )
    return {"status": "idle"}


def _compress_study(client: httpx.Client, base: str, study_id: str, transfer_syntax: str) -> tuple[int, int, int]:
    response = client.get(f"{base}/studies/{study_id}/instances")
    response.raise_for_status()
    instance_ids = response.json()
    if not isinstance(instance_ids, list):
        return 0, 1, 0

    compressed = 0
    skipped = 0
    failed = 0
    body = {"Transcode": transfer_syntax, "Force": True, "KeepSource": False}
    for instance_id in instance_ids:
        iid = str(instance_id).strip()
        if not iid:
            continue
        try:
            result = client.post(f"{base}/instances/{iid}/modify", json=body)
            if result.status_code == 200:
                compressed += 1
            else:
                detail = result.text[:200]
                if "same transfer syntax" in detail.lower() or result.status_code == 409:
                    skipped += 1
                else:
                    failed += 1
                    logger.warning("Compressão %s: HTTP %s — %s", iid, result.status_code, detail)
        except httpx.HTTPError as exc:
            failed += 1
            logger.warning("Compressão %s falhou: %s", iid, exc)
    return compressed, skipped, failed


def process_storage_batch() -> dict[str, Any]:
    cfg = get_storage_config()
    status = str(cfg.get("status") or "idle")
    if status != "running":
        return {"status": status, "processed": 0}

    queue = load_storage_queue()
    cursor = int(cfg.get("cursor") or 0)
    batch_size = max(1, int(cfg.get("batch_size") or 5))
    pause_seconds = max(0, int(cfg.get("pause_seconds") or 2))

    if cursor >= len(queue):
        update_storage_state(status="completed", last_run_at=utc_now_iso())
        return {"status": "completed", "processed": 0}

    stats = dict(cfg.get("stats") or {})
    processed = 0
    base = settings.orthanc_url.rstrip("/")

    with httpx.Client(timeout=300.0) as client:
        end = min(len(queue), cursor + batch_size)
        for index in range(cursor, end):
            item = queue[index]
            study_id = str(item.get("study_id") or "").strip()
            transfer_syntax = str(item.get("transfer_syntax") or "").strip()
            if not study_id or not transfer_syntax:
                stats["skipped"] = int(stats.get("skipped") or 0) + 1
                cursor = index + 1
                continue
            try:
                compressed, skipped, failed = _compress_study(client, base, study_id, transfer_syntax)
                stats["instances"] = int(stats.get("instances") or 0) + compressed
                if failed:
                    stats["failed"] = int(stats.get("failed") or 0) + 1
                elif compressed:
                    stats["compressed"] = int(stats.get("compressed") or 0) + 1
                else:
                    stats["skipped"] = int(stats.get("skipped") or 0) + 1
            except httpx.HTTPError as exc:
                stats["failed"] = int(stats.get("failed") or 0) + 1
                update_storage_state(last_error=str(exc), stats=stats)
            cursor = index + 1
            processed += 1
            if pause_seconds and index < end - 1:
                pass

    next_status = "completed" if cursor >= len(queue) else "running"
    update_storage_state(
        status=next_status,
        cursor=cursor,
        stats=stats,
        last_run_at=utc_now_iso() if next_status == "completed" else cfg.get("last_run_at", ""),
    )
    return {"status": next_status, "processed": processed, "cursor": cursor}


def maybe_start_scheduled_run() -> bool:
    cfg = get_storage_config()
    if not cfg.get("enabled"):
        return False
    if str(cfg.get("status") or "") in {"running", "paused"}:
        return False
    if not [rule for rule in (cfg.get("rules") or []) if rule.get("enabled", True)]:
        return False

    last_run = str(cfg.get("last_run_at") or cfg.get("started_at") or "").strip()
    interval_hours = max(1, int(cfg.get("run_interval_hours") or 24))
    if last_run:
        try:
            last_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - last_dt.astimezone(timezone.utc)).total_seconds()
            if elapsed < interval_hours * 3600:
                return False
        except ValueError:
            pass

    result = start_storage_run()
    return result.get("queue_total", 0) >= 0
