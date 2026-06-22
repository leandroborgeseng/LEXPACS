from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .config import settings
from .mwl_sql import utc_now_iso

AGE_BUCKETS = (
    ("0-7 dias", 0, 7),
    ("8-30 dias", 8, 30),
    ("31-90 dias", 31, 90),
    ("91-365 dias", 91, 365),
    ("> 1 ano", 366, None),
)


def _empty_age_counts() -> dict[str, int]:
    return {label: 0 for label, _, _ in AGE_BUCKETS} | {"Sem data": 0}


def _parse_dicom_date(value: str) -> date | None:
    raw = str(value or "").strip()
    if len(raw) < 8 or not raw[:8].isdigit():
        return None
    try:
        return datetime.strptime(raw[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _parse_orthanc_timestamp(value: str) -> date | None:
    raw = str(value or "").strip()
    if len(raw) < 8 or not raw[:8].isdigit():
        return None
    try:
        return datetime.strptime(raw[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _bucket_age(reference: date | None, today: date) -> str:
    if reference is None:
        return "Sem data"
    age_days = (today - reference).days
    if age_days < 0:
        return "0-7 dias"
    for label, low, high in AGE_BUCKETS:
        if high is None and age_days >= low:
            return label
        if high is not None and low <= age_days <= high:
            return label
    return "> 1 ano"


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def _disk_item(label: str, bytes_value: int) -> dict[str, Any]:
    return {
        "label": label,
        "bytes": bytes_value,
        "mb": round(bytes_value / (1024 * 1024), 2),
    }


async def collect_pacs_stats() -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    study_date_age = _empty_age_counts()
    received_age = _empty_age_counts()
    modality_studies: dict[str, set[str]] = defaultdict(set)

    async with httpx.AsyncClient(timeout=120.0) as client:
        base = settings.orthanc_url.rstrip("/")
        stats_resp = await client.get(f"{base}/statistics")
        stats_resp.raise_for_status()
        orthanc_stats = stats_resp.json()

        studies_resp = await client.post(
            f"{base}/tools/find",
            json={"Level": "Study", "Query": {}, "Expand": True},
        )
        studies_resp.raise_for_status()
        studies = studies_resp.json()

    series_count_by_modality: dict[str, int] = defaultdict(int)
    for study in studies:
        if not isinstance(study, dict):
            continue
        study_id = str(study.get("ID", "")).strip()
        tags = study.get("MainDicomTags", {}) if isinstance(study, dict) else {}
        study_date = _parse_dicom_date(tags.get("StudyDate", ""))
        received = _parse_orthanc_timestamp(study.get("LastUpdate", ""))
        study_date_age[_bucket_age(study_date, today)] += 1
        received_age[_bucket_age(received, today)] += 1
        modalities_raw = str(tags.get("ModalitiesInStudy", "")).strip()
        if modalities_raw:
            for modality in modalities_raw.split("\\"):
                mod = modality.strip().upper() or "OUTROS"
                if study_id:
                    modality_studies[mod].add(study_id)
                series_count_by_modality[mod] += 1
        elif study_id:
            modality_studies["OUTROS"].add(study_id)

    orthanc_bytes = int(orthanc_stats.get("TotalDiskSize") or 0)
    reports_bytes = _dir_size_bytes(Path(settings.reports_data_path))
    audit_bytes = _dir_size_bytes(Path(settings.audit_data_path))
    worklist_bytes = _dir_size_bytes(Path(settings.orthanc_worklist_path))

    disk_items = [
        _disk_item("Imagens DICOM", orthanc_bytes),
        _disk_item("Laudos (lex-reports)", reports_bytes),
        _disk_item("Auditoria (lex-audit)", audit_bytes),
        _disk_item("Worklist MWL", worklist_bytes),
    ]
    total_bytes = sum(item["bytes"] for item in disk_items)

    studies_by_modality = sorted(
        [
            {
                "modality": modality,
                "studies": len(modality_studies.get(modality, set())),
                "series": series_count_by_modality.get(modality, 0),
            }
            for modality in sorted(modality_studies)
        ],
        key=lambda item: (-item["studies"], item["modality"]),
    )

    return {
        "patients": int(orthanc_stats.get("CountPatients") or 0),
        "studies": int(orthanc_stats.get("CountStudies") or 0),
        "series": int(orthanc_stats.get("CountSeries") or 0),
        "instances": int(orthanc_stats.get("CountInstances") or 0),
        "studies_by_modality": studies_by_modality,
        "study_date_age": [{"label": label, "count": study_date_age[label]} for label in study_date_age],
        "received_age": [{"label": label, "count": received_age[label]} for label in received_age],
        "disk": disk_items,
        "disk_total_bytes": total_bytes,
        "disk_total_mb": round(total_bytes / (1024 * 1024), 2),
        "generated_at": utc_now_iso(),
    }
