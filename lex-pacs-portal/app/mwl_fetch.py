from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .mwl_connector import execute_select
from .mwl_drivers import DEFAULT_FIELD_MAPPING, MWL_COLUMN_FIELDS
from .mwl_sql import get_mwl_sql_config
from .mwl_store import fetch_mwl_rows as fetch_internal_rows

_SEX_ALIASES = {
    "M": "M",
    "MALE": "M",
    "MASC": "M",
    "MASCULINO": "M",
    "F": "F",
    "FEMALE": "F",
    "FEM": "F",
    "FEMININO": "F",
    "O": "O",
    "OTHER": "O",
    "OUTRO": "O",
    "OUTROS": "O",
}

_UID_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)+$")


@dataclass
class MwlSyncPlan:
    read: int = 0
    errors: int = 0
    rows_to_write: list[dict[str, Any]] = field(default_factory=list)

    @property
    def error_summary(self) -> str:
        if self.errors <= 0:
            return ""
        return "Itens pulados: accession vazio ou campo obrigatório nulo."


def _normalize_mapping(raw: dict[str, Any] | None) -> dict[str, str]:
    mapping = dict(DEFAULT_FIELD_MAPPING)
    if raw:
        for key in DEFAULT_FIELD_MAPPING:
            value = str(raw.get(key) or "").strip()
            if value:
                mapping[key] = value
    return mapping


def _status_tokens(mapping: dict[str, str], key: str) -> set[str]:
    parts = re.split(r"[,;|]", str(mapping.get(key) or ""))
    return {part.strip().upper() for part in parts if part.strip()}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _as_text(value)
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    digits = re.sub(r"\D", "", text)[:8]
    if len(digits) == 8:
        try:
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None
    return None


def _parse_time(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.strftime("%H%M%S")
    if isinstance(value, time):
        return value.strftime("%H%M%S")
    if isinstance(value, timedelta):
        total = int(value.total_seconds()) % 86400
        hh, rem = divmod(total, 3600)
        mm, ss = divmod(rem, 60)
        return f"{hh:02d}{mm:02d}{ss:02d}"
    text = _as_text(value)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 6:
        hh, mm, ss = int(digits[:2]), int(digits[2:4]), int(digits[4:6])
    elif len(digits) == 4:
        hh, mm, ss = int(digits[:2]), int(digits[2:4]), 0
    elif len(digits) == 2:
        hh, mm, ss = int(digits), 0, 0
    else:
        return None
    if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
        return None
    return f"{hh:02d}{mm:02d}{ss:02d}"


def _normalize_sex(value: Any) -> str:
    token = _as_text(value).upper()
    if not token:
        return ""
    return _SEX_ALIASES.get(token, token[:16])


def stable_study_uid(accession: str) -> str:
    """UID DICOM estável por accession. A origem real pode não ter Study Instance UID."""
    digest = hashlib.sha256(b"lexpacs-mwl|" + accession.encode("utf-8")).digest()
    number = int.from_bytes(digest[:16], "big")
    return f"2.25.{number}"


def _study_uid(value: Any, accession: str) -> str:
    text = _as_text(value)
    if _UID_RE.match(text) and len(text) <= 64:
        return text
    return stable_study_uid(accession)


def schedule_window(cfg: dict[str, Any]) -> tuple[date, date]:
    tz_name = str(cfg.get("schedule_timezone") or "America/Sao_Paulo")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/Sao_Paulo")
    today = datetime.now(tz).date()
    days = int(cfg.get("schedule_window_days") or 2)
    days = max(1, days)
    return today, today + timedelta(days=days - 1)


def _map_row(raw: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    lower_raw = {str(key).lower(): value for key, value in raw.items()}
    mapped: dict[str, Any] = {}
    for column_field in MWL_COLUMN_FIELDS:
        column = mapping.get(column_field) or column_field
        mapped[column_field] = lower_raw.get(str(column).lower())
    return mapped


def _prepare_row(
    raw: dict[str, Any],
    cfg: dict[str, Any],
    *,
    strict: bool,
    today: date,
    window_end: date,
) -> tuple[str, dict[str, Any] | None]:
    """Retorna ('write'|'exclude'|'error', linha normalizada ou None)."""
    mapping = _normalize_mapping(cfg.get("field_mapping"))
    accession = _as_text(raw.get("accession_number"))[:32]
    if not accession:
        return "error", None

    modality = _as_text(raw.get("modality")).upper()[:16]
    station = _as_text(raw.get("station_aet")).upper()[:16]
    for route in cfg.get("modality_routes") or []:
        route_mod = str(route.get("modality") or "").strip().upper()
        route_station = str(route.get("station_aet") or "").strip().upper()
        if route_mod and route_mod == modality and route_station:
            station = route_station[:16]
            break

    scheduled = _parse_date(raw.get("scheduled_date"))
    scheduled_time = _parse_time(raw.get("scheduled_time"))
    birth = _parse_date(raw.get("patient_birth_date"))
    sex = _normalize_sex(raw.get("patient_sex"))
    patient_id = _as_text(raw.get("patient_id"))[:64]
    patient_name = _as_text(raw.get("patient_name"))[:128]
    description = _as_text(raw.get("procedure_description"))[:128]
    status_value = _as_text(raw.get("status")).upper()

    if strict:
        missing = (
            not patient_id
            or not patient_name
            or birth is None
            or not sex
            or not modality
            or not station
            or scheduled is None
            or not scheduled_time
        )
        if missing:
            return "error", None
    else:
        patient_id = patient_id or "UNKNOWN"
        patient_name = patient_name or "UNKNOWN"
        modality = modality or "OT"
        station = station or "UNKNOWN"
        scheduled = scheduled or today
        scheduled_time = scheduled_time or "000000"

    normalized = {
        "accession_number": accession,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "patient_birth_date": birth.strftime("%Y%m%d") if birth else "",
        "patient_sex": sex,
        "modality": modality,
        "station_aet": station,
        "procedure_description": description,
        "scheduled_date": scheduled,
        "scheduled_time": scheduled_time,
        "study_instance_uid": _study_uid(raw.get("study_instance_uid"), accession),
        "status": status_value,
    }

    cancelled = _status_tokens(mapping, "status_cancelled")
    performed = _status_tokens(mapping, "status_performed")
    if status_value and (status_value in cancelled or status_value in performed):
        return "exclude", normalized

    filters = [str(item).strip().upper() for item in (cfg.get("modality_filter") or []) if str(item).strip()]
    if filters and modality not in filters:
        return "exclude", normalized

    if scheduled < today or scheduled > window_end:
        return "exclude", normalized
    return "write", normalized


def read_source_rows(cfg: dict[str, Any], *, limit: int | None = None) -> list[dict[str, Any]]:
    mode = str(cfg.get("mode") or "table")
    if mode == "table":
        rows = fetch_internal_rows()
        if limit is not None:
            return rows[:limit]
        return rows
    sql = str(cfg.get("custom_sql") or "").strip()
    return execute_select(cfg, sql, limit=limit)


def load_mwl_sync_plan(*, preview_limit: int | None = None) -> MwlSyncPlan:
    cfg = get_mwl_sql_config()
    if not cfg.get("enabled", True):
        return MwlSyncPlan()

    raw_rows = read_source_rows(cfg, limit=preview_limit)
    strict = str(cfg.get("mode") or "table") != "table"
    if strict:
        mapping = _normalize_mapping(cfg.get("field_mapping"))
        prepared = [_map_row(item, mapping) for item in raw_rows]
    else:
        prepared = [dict(item) for item in raw_rows]

    today, window_end = schedule_window(cfg)
    writes: dict[str, dict[str, Any]] = {}
    excluded: set[str] = set()
    errors = 0
    for raw in prepared:
        kind, row = _prepare_row(raw, cfg, strict=strict, today=today, window_end=window_end)
        if kind == "error" or row is None:
            errors += 1
            continue
        accession = str(row.get("accession_number") or "")
        if kind == "exclude":
            excluded.add(accession)
            continue
        writes[accession] = row
    for accession in excluded:
        writes.pop(accession, None)
    return MwlSyncPlan(read=len(prepared), errors=errors, rows_to_write=list(writes.values()))


def fetch_mwl_source_rows(*, preview_limit: int | None = None) -> list[dict[str, Any]]:
    return load_mwl_sync_plan(preview_limit=preview_limit).rows_to_write
