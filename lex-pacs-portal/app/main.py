from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import (
    VIEWER_COOKIE_NAME,
    birth_dates_match,
    create_access_token,
    create_viewer_token,
    get_current_patient,
    normalize_birth_date,
    viewer_token_matches_uri,
)
from .admin import router as admin_router
from .audit import log_event
from .clinical_session import ClinicalUser
from .clinical_session import (
    authenticate_clinical,
    create_clinical_session,
    session_cookie_kwargs,
    CLINICAL_COOKIE_NAME,
)
from .clinical_auth import (
    clinical_user_from_request,
    oidc_status,
    require_clinical_user,
)
from .config import settings
from .reports import router as reports_router
from .mwl_scheduler import start_mwl_scheduler
from .orthanc_client import OrthancClient
from .report_storage import get_patient_report, is_visible_to_patient, load_report, pdf_path

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="LEX PACS Portal do Paciente",
    version="0.2.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(admin_router)
app.include_router(reports_router)

orthanc = OrthancClient()


@app.on_event("startup")
async def on_startup() -> None:
    start_mwl_scheduler()


class LoginRequest(BaseModel):
    patient_id: str = Field(min_length=1, max_length=64)
    birth_date: str = Field(min_length=8, max_length=10)
    access_code: str | None = Field(default=None, max_length=64)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    patient_id: str
    patient_name: str


class ViewerSessionResponse(BaseModel):
    redirect_url: str


class PatientReportResponse(BaseModel):
    study_instance_uid: str
    content_html: str = ""
    has_pdf: bool = False
    signed_by: str = ""
    signed_crm: str = ""
    signed_at: str | None = None
    pdf_filename: str | None = None


class ClinicalLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    next: str = Field(default="/viewer/", max_length=512)


class ClinicalLoginResponse(BaseModel):
    redirect_url: str
    username: str
    groups: list[str]
    access_token: str


async def _patient_owns_study(patient_id: str, study_instance_uid: str) -> None:
    studies = await orthanc.find_studies_for_patient(patient_id)
    allowed = {study.get("study_instance_uid") for study in studies}
    if study_instance_uid not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Exame não autorizado.")


@app.get("/api/health")
async def health() -> dict:
    storage_ok = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.orthanc_url}/system")
            storage_ok = response.status_code == 200
    except httpx.HTTPError:
        storage_ok = False
    return {"status": "ok", "storage": storage_ok, "version": settings.lex_pacs_version}


@app.get("/api/auth/validate-viewer-cookie")
async def validate_viewer_cookie(request: Request) -> Response:
    """Usado pelo gateway (auth_request interno) para liberar viewer e imagens ao paciente."""
    token = request.cookies.get(VIEWER_COOKIE_NAME)
    uri = request.headers.get("x-original-uri", request.url.path)
    if token and viewer_token_matches_uri(token, uri):
        return Response(status_code=200)
    return Response(status_code=401)


@app.get("/api/auth/validate-dicom-access")
async def validate_dicom_access(request: Request) -> Response:
    """Viewer/DICOMweb: sessão clínica, cookie do paciente ou Bearer."""
    user = clinical_user_from_request(request)
    if user:
        return Response(
            status_code=200,
            headers={
                "X-Clinic-User": user.username,
                "X-Clinic-Groups": ",".join(user.groups),
            },
        )

    token = request.cookies.get(VIEWER_COOKIE_NAME)
    uri = request.headers.get("x-original-uri", request.url.path)
    if token and viewer_token_matches_uri(token, uri):
        return Response(status_code=200)

    return Response(status_code=401)


@app.get("/api/auth/validate-clinical")
async def validate_clinical_auth(request: Request) -> Response:
    """Usado pelo gateway: sessão clínica ou Bearer OIDC."""
    user = clinical_user_from_request(request)
    if user:
        return Response(
            status_code=200,
            headers={
                "X-Clinic-User": user.username,
                "X-Clinic-Groups": ",".join(user.groups),
            },
        )
    return Response(status_code=401)


@app.post("/api/auth/clinical/login", response_model=ClinicalLoginResponse)
async def clinical_login(body: ClinicalLoginRequest) -> JSONResponse:
    user = await authenticate_clinical(body.username, body.password)
    token = create_clinical_session(user.username, user.groups, user.auth_method)
    redirect = body.next.strip() if body.next.startswith("/") and not body.next.startswith("//") else "/viewer/"
    log_event("clinical_login", user.username, auth_method=user.auth_method)
    response = JSONResponse(
        content=ClinicalLoginResponse(
            redirect_url=redirect,
            username=user.username,
            groups=user.groups,
            access_token=token,
        ).model_dump()
    )
    response.set_cookie(key=CLINICAL_COOKIE_NAME, value=token, **session_cookie_kwargs())
    return response


@app.post("/api/auth/clinical/logout")
async def clinical_logout() -> JSONResponse:
    response = JSONResponse(content={"ok": True})
    response.delete_cookie(key=CLINICAL_COOKIE_NAME, path="/")
    return response


@app.get("/clinica/login")
@app.get("/clinica/")
async def clinica_login_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "clinica.html")


@app.get("/api/auth/clinical/config")
async def clinical_auth_config() -> dict:
    return oidc_status()


@app.get("/api/auth/clinical/me")
async def clinical_me(clinical_user: ClinicalUser = Depends(require_clinical_user)) -> dict:
    return {
        "username": clinical_user.username,
        "groups": clinical_user.groups,
        "auth_method": clinical_user.auth_method,
    }


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    patient_id = body.patient_id.strip()
    patients = await orthanc.find_patients_by_id(patient_id)

    if not patients:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Paciente não encontrado ou dados incorretos.",
        )

    patient = patients[0]
    dicom_birth = patient.get("birth_date", "")
    authenticated = False

    if dicom_birth:
        try:
            normalize_birth_date(body.birth_date)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        authenticated = birth_dates_match(dicom_birth, body.birth_date)
    elif settings.portal_fallback_code and body.access_code == settings.portal_fallback_code:
        authenticated = True

    if not authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Paciente não encontrado ou dados incorretos.",
        )

    token = create_access_token(patient_id, patient.get("patient_name", ""))
    return LoginResponse(
        access_token=token,
        patient_id=patient_id,
        patient_name=patient.get("patient_name", ""),
    )


@app.get("/api/studies")
async def list_studies(patient: dict = Depends(get_current_patient)) -> dict:
    studies = await orthanc.find_studies_for_patient(patient["sub"])
    enriched = []
    for study in studies:
        uid = study.get("study_instance_uid", "")
        report = load_report(uid) if uid else {}
        enriched.append(
            {
                **study,
                "report_available": is_visible_to_patient(report),
            }
        )
    return {"patient_id": patient["sub"], "patient_name": patient.get("name", ""), "studies": enriched}


@app.get("/api/studies/{study_instance_uid}/report", response_model=PatientReportResponse)
async def patient_report(
    study_instance_uid: str,
    patient: dict = Depends(get_current_patient),
) -> PatientReportResponse:
    await _patient_owns_study(patient["sub"], study_instance_uid)
    return PatientReportResponse(**get_patient_report(study_instance_uid))


@app.get("/api/studies/{study_instance_uid}/report/pdf")
async def patient_report_pdf(
    study_instance_uid: str,
    patient: dict = Depends(get_current_patient),
) -> FileResponse:
    await _patient_owns_study(patient["sub"], study_instance_uid)
    payload = get_patient_report(study_instance_uid)
    if not payload.get("has_pdf"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF não disponível.")
    return FileResponse(
        pdf_path(study_instance_uid),
        media_type="application/pdf",
        filename=payload.get("pdf_filename") or "laudo.pdf",
    )


@app.post("/api/studies/{study_instance_uid}/viewer-session", response_model=ViewerSessionResponse)
async def create_viewer_session(
    study_instance_uid: str,
    patient: dict = Depends(get_current_patient),
) -> JSONResponse:
    studies = await orthanc.find_studies_for_patient(patient["sub"])
    allowed_uids = {study.get("study_instance_uid") for study in studies}
    if study_instance_uid not in allowed_uids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Exame não autorizado.")

    viewer_token = create_viewer_token(patient["sub"], study_instance_uid)
    redirect_url = f"/viewer/?StudyInstanceUIDs={study_instance_uid}"
    log_event(
        "study_open",
        patient["sub"],
        study_instance_uid=study_instance_uid,
        portal="patient",
    )
    response = JSONResponse(
        content=ViewerSessionResponse(redirect_url=redirect_url).model_dump()
    )
    response.set_cookie(
        key=VIEWER_COOKIE_NAME,
        value=viewer_token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.viewer_token_expire_minutes * 60,
        path="/",
    )
    return response


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
