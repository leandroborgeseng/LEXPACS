from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from .mwl_connector import execute_select
from .mwl_drivers import DEFAULT_FIELD_MAPPING, MWL_FIELDS
from .mwl_sql import get_mwl_sql_config
from .mwl_store import fetch_mwl_rows as fetch_internal_rows


def _normalize_mapping(raw: dict[str, Any] | None) -> dict[str, str]:
    mapping = dict(DEFAULT_FIELD_MAPPING)
    if raw:
        for field in MWL_FIELDS:
            value = str(raw.get(field) or "").strip()
            if value:
                mapping[field] = value
    return mapping


def _parse_scheduled_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return date.today()
    if len(text) >= 10 and text[4] == "-":
        return date.fromisoformat(text[:10])
    digits = re.sub(r"\D", "", text)[:8]
    if len(digits) == 8:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    return date.today()


def _map_row(raw: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    lower_raw = {str(k).lower(): v for k, v in raw.items()}
    mapped: dict[str, Any] = {}
    for field, column in mapping.items():
        mapped[field] = lower_raw.get(column.lower(), "")
    return mapped


def _apply_modality_rules(row: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any] | None:
    modality = str(row.get("modality") or "").strip().upper() or "OT"
    row["modality"] = modality

    filters = [str(m).strip().upper() for m in (cfg.get("modality_filter") or []) if str(m).strip()]
    if filters and modality not in filters:
        return None

    routes = cfg.get("modality_routes") or []
    for route in routes:
        route_mod = str(route.get("modality") or "").strip().upper()
        route_station = str(route.get("station_aet") or "").strip().upper()
        if route_mod and route_mod == modality and route_station:
            row["station_aet"] = route_station
            break

    row["accession_number"] = str(row.get("accession_number") or "").strip()[:32]
    if not row["accession_number"]:
        return None

    row["patient_id"] = str(row.get("patient_id") or "").strip()[:64] or "UNKNOWN"
    row["patient_name"] = str(row.get("patient_name") or "").strip()[:128] or "UNKNOWN"
    row["station_aet"] = str(row.get("station_aet") or "").strip().upper()[:16] or "UNKNOWN"
    row["procedure_description"] = str(row.get("procedure_description") or "").strip()[:128]
    row["scheduled_date"] = _parse_scheduled_date(row.get("scheduled_date"))
    return row


def fetch_mwl_source_rows(*, preview_limit: int | None = None) -> list[dict[str, Any]]:
    cfg = get_mwl_sql_config()
    if not cfg.get("enabled", True):
        return []

    mode = str(cfg.get("mode") or "table")
    mapping = _normalize_mapping(cfg.get("field_mapping"))

    if mode == "table":
        rows = fetch_internal_rows()
        if preview_limit is not None:
            rows = rows[:preview_limit]
    else:
        sql = str(cfg.get("custom_sql") or "").strip()
        raw_rows = execute_select(cfg, sql, limit=preview_limit)
        rows = [_map_row(item, mapping) for item in raw_rows]

    result: list[dict[str, Any]] = []
    for row in rows:
        normalized = _apply_modality_rules(dict(row), cfg)
        if normalized:
            result.append(normalized)
    return result
