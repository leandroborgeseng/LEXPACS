from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .hl7_settings import get_hl7_config, record_hl7_message
from .lex_settings import get_equipment
from .mwl_store import delete_mwl_row, upsert_mwl_row
from .mwl_scheduler import run_mwl_sync

SEGMENT_TERMINATORS = re.compile(r"[\r\n]+")
CANCEL_CODES = frozenset({"CA", "OC", "OD", "DC"})
UPSERT_CODES = frozenset({"NW", "XO", "XX", "SC", "RP", "RE", "NA", "SN"})


@dataclass
class Hl7ParseResult:
    message_id: str
    message_type: str
    order_control: str
    accession_number: str
    patient_id: str
    patient_name: str
    modality: str
    station_aet: str
    procedure_description: str
    scheduled_date: date
    is_cancel: bool


def _split_segments(raw: str) -> list[str]:
    return [segment for segment in SEGMENT_TERMINATORS.split(raw.strip()) if segment.strip()]


def _fields(segment: str) -> list[str]:
    return segment.split("|")


def _component(field: str, index: int = 0) -> str:
    parts = field.split("^")
    if index >= len(parts):
        return ""
    return parts[index].strip()


def _segment_fields(segments: list[str], name: str) -> list[str] | None:
    prefix = f"{name}|"
    for segment in segments:
        if segment.startswith(prefix) or segment == name:
            return _fields(segment)
    return None


def _parse_hl7_datetime(value: str) -> date:
    cleaned = re.sub(r"[^0-9]", "", value or "")[:8]
    if len(cleaned) == 8:
        return datetime.strptime(cleaned, "%Y%m%d").date()
    return date.today()


def _normalize_modality(value: str) -> str:
    mod = value.strip().upper()
    if len(mod) <= 16 and mod.isalnum():
        return mod
    return ""


def _resolve_modality(obr: list[str]) -> str:
    for idx in (24, 4):
        if idx >= len(obr):
            continue
        if idx == 4:
            candidate = _normalize_modality(_component(obr[4], 0))
            if candidate in {"CR", "DX", "CT", "MR", "US", "MG", "PT", "NM", "RF", "XA", "OT"}:
                return candidate
            continue
        candidate = _normalize_modality(obr[idx])
        if candidate:
            return candidate
    return "OT"


def _resolve_station(modality: str, obr: list[str], cfg: dict[str, Any]) -> str:
    if len(obr) > 21:
        station = _component(obr[21], 0).upper()
        if station:
            return station[:16]
    if cfg.get("map_modality_to_station", True):
        mod = modality.upper()
        for item in get_equipment():
            item_mod = str(item.get("modality", "")).upper()
            if item_mod == mod or (mod in {"CR", "DX"} and item_mod in {"CR", "DX"}):
                return str(item.get("aet", "")).upper()[:16]
    default = str(cfg.get("default_station_aet", "")).strip().upper()
    if default:
        return default[:16]
    return "UNKNOWN"


def parse_orm_message(raw: str) -> Hl7ParseResult:
    segments = _split_segments(raw)
    if not segments:
        raise ValueError("Mensagem HL7 vazia.")

    msh = _segment_fields(segments, "MSH")
    if not msh or len(msh) < 9:
        raise ValueError("Segmento MSH ausente ou incompleto.")

    message_type = _component(msh[8], 0)
    trigger = _component(msh[8], 1)
    if message_type != "ORM":
        raise ValueError(f"Tipo HL7 não suportado: {message_type}^{trigger}")

    message_id = msh[9] if len(msh) > 9 else ""

    pid = _segment_fields(segments, "PID") or []
    patient_id = _component(pid[3], 0) if len(pid) > 3 else ""
    patient_name = pid[5] if len(pid) > 5 else ""

    orc = _segment_fields(segments, "ORC") or []
    order_control = orc[1].strip().upper() if len(orc) > 1 else "NW"

    obr = _segment_fields(segments, "OBR") or []
    accession = ""
    if len(obr) > 3 and obr[3].strip():
        accession = _component(obr[3], 0)
    elif len(obr) > 2 and obr[2].strip():
        accession = _component(obr[2], 0)
    elif len(orc) > 3 and orc[3].strip():
        accession = _component(orc[3], 0)
    if not accession:
        raise ValueError("Accession number não encontrado (OBR-3/ORC-3).")

    cfg = get_hl7_config()
    modality = _resolve_modality(obr)
    station_aet = _resolve_station(modality, obr, cfg)

    scheduled_raw = ""
    if len(obr) > 7 and obr[7].strip():
        scheduled_raw = obr[7]
    elif len(orc) > 7 and orc[7].strip():
        scheduled_raw = orc[7]
    scheduled_date = _parse_hl7_datetime(scheduled_raw)

    procedure = ""
    if len(obr) > 4 and obr[4].strip():
        procedure = _component(obr[4], 1) or _component(obr[4], 0)
    elif len(obr) > 31 and obr[31].strip():
        procedure = _component(obr[31], 0)
    procedure = procedure[:128]

    is_cancel = order_control in CANCEL_CODES
    if not is_cancel and order_control not in UPSERT_CODES:
        # Perfil conservador: trata desconhecido como upsert se não for cancelamento explícito
        is_cancel = False

    return Hl7ParseResult(
        message_id=message_id,
        message_type=f"{message_type}^{trigger}",
        order_control=order_control,
        accession_number=accession[:32],
        patient_id=patient_id[:64] or "UNKNOWN",
        patient_name=patient_name[:128] or "UNKNOWN",
        modality=modality,
        station_aet=station_aet,
        procedure_description=procedure,
        scheduled_date=scheduled_date,
        is_cancel=is_cancel,
    )


def build_ack(raw: str, ack_code: str = "AA", text: str = "") -> str:
    segments = _split_segments(raw)
    msh = _segment_fields(segments, "MSH") or []
    cfg = get_hl7_config()
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    message_id = msh[9] if len(msh) > 9 else "1"
    sending_app = cfg.get("sending_application", "LEXPACS")
    sending_fac = cfg.get("sending_facility", "LEX")
    remote_app = msh[2] if len(msh) > 2 else "RIS"
    remote_fac = msh[3] if len(msh) > 3 else "CLINIC"
    trigger = _component(msh[8], 1) if len(msh) > 8 else "O01"
    ack = (
        f"MSH|^~\\&|{sending_app}|{sending_fac}|{remote_app}|{remote_fac}|{now}"
        f"||ACK^{trigger}|{message_id}|P|2.5\r"
        f"MSA|{ack_code}|{message_id}"
    )
    if text:
        ack += f"|{text[:80]}"
    ack += "\r"
    return ack


def wrap_mllp(payload: str) -> bytes:
    body = payload if payload.endswith("\r") else payload + "\r"
    return b"\x0b" + body.encode("utf-8") + b"\x1c\x0d"


def unwrap_mllp(data: bytes) -> str:
    start = data.find(b"\x0b")
    end = data.find(b"\x1c")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Frame MLLP inválido.")
    return data[start + 1 : end].decode("utf-8", errors="replace")


def process_hl7_orm(raw: str, *, actor: str = "hl7") -> dict[str, Any]:
    try:
        parsed = parse_orm_message(raw)
        if parsed.is_cancel:
            deleted = delete_mwl_row(parsed.accession_number)
            action = "cancelled" if deleted else "cancel_missing"
        else:
            upsert_mwl_row(
                {
                    "accession_number": parsed.accession_number,
                    "patient_id": parsed.patient_id,
                    "patient_name": parsed.patient_name,
                    "modality": parsed.modality,
                    "station_aet": parsed.station_aet,
                    "procedure_description": parsed.procedure_description,
                    "scheduled_date": parsed.scheduled_date,
                }
            )
            action = "upserted"

        sync_result: dict[str, Any] | None = None
        cfg = get_hl7_config()
        if cfg.get("auto_sync", True):
            sync_result = run_mwl_sync(actor=actor)

        stats = record_hl7_message(
            accession=parsed.accession_number,
            control=parsed.order_control,
            message_type=parsed.message_type,
            error="",
        )
        return {
            "ok": True,
            "action": action,
            "accession_number": parsed.accession_number,
            "order_control": parsed.order_control,
            "modality": parsed.modality,
            "station_aet": parsed.station_aet,
            "sync": sync_result,
            "stats": stats,
        }
    except Exception as exc:
        stats = record_hl7_message(error=str(exc))
        raise ValueError(str(exc)) from exc


def process_mllp_frame(data: bytes, *, actor: str = "hl7") -> bytes:
    try:
        raw = unwrap_mllp(data)
        process_hl7_orm(raw, actor=actor)
        return wrap_mllp(build_ack(raw, "AA"))
    except Exception as exc:
        try:
            raw = unwrap_mllp(data)
        except Exception:
            raw = ""
        ack = build_ack(raw or "MSH|^~\\&|LEXPACS|LEX|RIS|CLINIC|000000000000||ORM^O01|0|P|2.5", "AE", str(exc))
        return wrap_mllp(ack)
