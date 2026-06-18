from __future__ import annotations

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .audit import log_event
from .clinical_auth import get_optional_clinical_user
from .config import settings
from .orthanc_client import OrthancClient
from .report_storage import (
    get_patient_report,
    load_report,
    pdf_path,
    release_to_patient,
    revoke_patient_visibility,
    save_draft,
    save_pdf,
    sign_report,
    validate_study_uid,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])
orthanc = OrthancClient()


class ReportResponse(BaseModel):
    study_instance_uid: str
    status: str
    content_html: str = ""
    author_name: str = ""
    signed_by: str = ""
    signed_crm: str = ""
    signed_at: str | None = None
    has_pdf: bool = False
    pdf_filename: str | None = None
    visible_to_patient: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class SaveDraftRequest(BaseModel):
    content_html: str = ""
    author_name: str = Field(default="", max_length=128)


class SignReportRequest(BaseModel):
    signed_by: str = Field(min_length=1, max_length=128)
    signed_crm: str = Field(default="", max_length=32)


async def _ensure_study_exists(study_uid: str) -> None:
    validate_study_uid(study_uid)
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{settings.orthanc_url}/tools/find",
            json={"Level": "Study", "Query": {"StudyInstanceUID": study_uid}},
        )
        response.raise_for_status()
        if not response.json():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Exame não encontrado.",
            )


def _to_response(data: dict) -> ReportResponse:
    return ReportResponse(
        study_instance_uid=data.get("study_instance_uid", ""),
        status=data.get("status", "draft"),
        content_html=data.get("content_html", ""),
        author_name=data.get("author_name", ""),
        signed_by=data.get("signed_by", ""),
        signed_crm=data.get("signed_crm", ""),
        signed_at=data.get("signed_at"),
        has_pdf=bool(data.get("has_pdf")),
        pdf_filename=data.get("pdf_filename"),
        visible_to_patient=bool(data.get("visible_to_patient")),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


@router.get("/{study_instance_uid}", response_model=ReportResponse)
async def get_report(study_instance_uid: str, request: Request) -> ReportResponse:
    await _ensure_study_exists(study_instance_uid)
    user = get_optional_clinical_user(request)
    if user:
        log_event(
            "study_open",
            user.username,
            study_instance_uid=study_instance_uid,
            auth_method=user.auth_method,
        )
    return _to_response(load_report(study_instance_uid))


@router.put("/{study_instance_uid}", response_model=ReportResponse)
async def put_report(study_instance_uid: str, body: SaveDraftRequest) -> ReportResponse:
    await _ensure_study_exists(study_instance_uid)
    data = save_draft(study_instance_uid, body.content_html, body.author_name)
    return _to_response(data)


@router.post("/{study_instance_uid}/sign", response_model=ReportResponse)
async def post_sign(
    study_instance_uid: str,
    body: SignReportRequest,
    request: Request,
) -> ReportResponse:
    await _ensure_study_exists(study_instance_uid)
    data = sign_report(study_instance_uid, body.signed_by, body.signed_crm)
    user = get_optional_clinical_user(request)
    log_event(
        "report_signed",
        user.username if user else body.signed_by,
        study_instance_uid=study_instance_uid,
        signed_by=body.signed_by,
        auth_method=user.auth_method if user else "unknown",
    )
    return _to_response(data)


@router.post("/{study_instance_uid}/pdf", response_model=ReportResponse)
async def post_pdf(
    study_instance_uid: str,
    file: UploadFile = File(...),
) -> ReportResponse:
    await _ensure_study_exists(study_instance_uid)
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Envie um arquivo PDF.",
        )
    pdf_bytes = await file.read()
    data = save_pdf(study_instance_uid, pdf_bytes, file.filename or "report.pdf")
    return _to_response(data)


@router.get("/{study_instance_uid}/pdf")
async def get_pdf(study_instance_uid: str, request: Request) -> FileResponse:
    await _ensure_study_exists(study_instance_uid)
    report = load_report(study_instance_uid)
    if not report.get("has_pdf"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF não anexado.")
    user = get_optional_clinical_user(request)
    if user:
        log_event(
            "export_pdf",
            user.username,
            study_instance_uid=study_instance_uid,
            auth_method=user.auth_method,
        )
    path = pdf_path(study_instance_uid)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=report.get("pdf_filename") or "laudo.pdf",
    )


@router.post("/{study_instance_uid}/release", response_model=ReportResponse)
async def post_release(study_instance_uid: str) -> ReportResponse:
    await _ensure_study_exists(study_instance_uid)
    data = release_to_patient(study_instance_uid)
    return _to_response(data)


@router.post("/{study_instance_uid}/revoke-patient", response_model=ReportResponse)
async def post_revoke_patient(study_instance_uid: str) -> ReportResponse:
    await _ensure_study_exists(study_instance_uid)
    data = revoke_patient_visibility(study_instance_uid)
    return _to_response(data)
