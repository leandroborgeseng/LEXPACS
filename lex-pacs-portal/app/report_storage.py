from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from .config import settings

_STUDY_UID_PATTERN = re.compile(r"^[0-9]+(\.[0-9]+)+$")
_MAX_HTML_BYTES = 512_000
_MAX_PDF_BYTES = 20 * 1024 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_study_uid(study_uid: str) -> str:
    study_uid = study_uid.strip()
    if not _STUDY_UID_PATTERN.match(study_uid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identificador de exame inválido.",
        )
    return study_uid


def _study_dir(study_uid: str) -> Path:
    base = Path(settings.reports_data_path)
    return base / study_uid


def _report_file(study_uid: str) -> Path:
    return _study_dir(study_uid) / "report.json"


def _pdf_file(study_uid: str) -> Path:
    return _study_dir(study_uid) / "report.pdf"


def _default_report(study_uid: str) -> dict[str, Any]:
    now = _utc_now()
    return {
        "study_instance_uid": study_uid,
        "status": "draft",
        "content_html": "",
        "author_name": "",
        "signed_by": "",
        "signed_crm": "",
        "signed_at": None,
        "has_pdf": False,
        "pdf_filename": None,
        "pdf_sha256": None,
        "visible_to_patient": False,
        "created_at": now,
        "updated_at": now,
    }


def load_report(study_uid: str) -> dict[str, Any]:
    study_uid = validate_study_uid(study_uid)
    path = _report_file(study_uid)
    if not path.is_file():
        return _default_report(study_uid)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível ler o laudo.",
        ) from exc
    data.setdefault("study_instance_uid", study_uid)
    return data


def save_draft(study_uid: str, content_html: str, author_name: str) -> dict[str, Any]:
    study_uid = validate_study_uid(study_uid)
    if len(content_html.encode("utf-8")) > _MAX_HTML_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Conteúdo do laudo excede o tamanho máximo permitido.",
        )

    report = load_report(study_uid)
    if report.get("status") == "signed":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Laudo assinado não pode ser alterado.",
        )

    now = _utc_now()
    if not report.get("created_at"):
        report["created_at"] = now
    report.update(
        {
            "content_html": content_html,
            "author_name": author_name.strip(),
            "status": "draft",
            "updated_at": now,
        }
    )
    _write_report(study_uid, report)
    return report


def sign_report(study_uid: str, signed_by: str, signed_crm: str = "") -> dict[str, Any]:
    study_uid = validate_study_uid(study_uid)
    report = load_report(study_uid)
    if report.get("status") == "signed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Laudo já está assinado.",
        )

    has_content = bool((report.get("content_html") or "").strip()) or report.get("has_pdf")
    if not has_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe o texto do laudo ou anexe um PDF antes de assinar.",
        )

    signed_by = signed_by.strip()
    if not signed_by:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe o nome do radiologista para assinar.",
        )

    now = _utc_now()
    report.update(
        {
            "status": "signed",
            "signed_by": signed_by,
            "signed_crm": signed_crm.strip(),
            "signed_at": now,
            "updated_at": now,
        }
    )
    _write_report(study_uid, report)
    return report


def save_pdf(study_uid: str, pdf_bytes: bytes, original_filename: str) -> dict[str, Any]:
    study_uid = validate_study_uid(study_uid)
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O arquivo deve ser um PDF válido.",
        )
    if len(pdf_bytes) > _MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF excede o tamanho máximo de 20 MB.",
        )

    report = load_report(study_uid)
    if report.get("status") == "signed":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Laudo assinado não pode receber novo PDF.",
        )

    study_dir = _study_dir(study_uid)
    study_dir.mkdir(parents=True, exist_ok=True)
    _pdf_file(study_uid).write_bytes(pdf_bytes)

    now = _utc_now()
    if not report.get("created_at"):
        report["created_at"] = now
    report.update(
        {
            "has_pdf": True,
            "pdf_filename": Path(original_filename).name or "report.pdf",
            "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
            "updated_at": now,
        }
    )
    _write_report(study_uid, report)
    return report


def pdf_path(study_uid: str) -> Path:
    study_uid = validate_study_uid(study_uid)
    path = _pdf_file(study_uid)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF do laudo não encontrado.",
        )
    return path


def is_visible_to_patient(report: dict[str, Any]) -> bool:
    return report.get("status") == "signed" and bool(report.get("visible_to_patient"))


def release_to_patient(study_uid: str) -> dict[str, Any]:
    study_uid = validate_study_uid(study_uid)
    report = load_report(study_uid)
    if report.get("status") != "signed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assine o laudo antes de liberar ao paciente.",
        )
    report["visible_to_patient"] = True
    report["updated_at"] = _utc_now()
    _write_report(study_uid, report)
    return report


def revoke_patient_visibility(study_uid: str) -> dict[str, Any]:
    study_uid = validate_study_uid(study_uid)
    report = load_report(study_uid)
    report["visible_to_patient"] = False
    report["updated_at"] = _utc_now()
    _write_report(study_uid, report)
    return report


def get_patient_report(study_uid: str) -> dict[str, Any]:
    study_uid = validate_study_uid(study_uid)
    report = load_report(study_uid)
    if not is_visible_to_patient(report):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Laudo não disponível.",
        )
    return {
        "study_instance_uid": study_uid,
        "content_html": report.get("content_html", ""),
        "has_pdf": bool(report.get("has_pdf")),
        "signed_by": report.get("signed_by", ""),
        "signed_crm": report.get("signed_crm", ""),
        "signed_at": report.get("signed_at"),
        "pdf_filename": report.get("pdf_filename"),
    }


def _write_report(study_uid: str, report: dict[str, Any]) -> None:
    study_dir = _study_dir(study_uid)
    study_dir.mkdir(parents=True, exist_ok=True)
    path = _report_file(study_uid)
    try:
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível salvar o laudo.",
        ) from exc
