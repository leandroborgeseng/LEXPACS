from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

security = HTTPBearer(auto_error=False)

VIEWER_COOKIE_NAME = "lex_viewer_token"


def normalize_birth_date(value: str) -> str:
    """Converte entrada do usuário para DICOM YYYYMMDD."""
    value = value.strip()
    if "/" in value or "-" in value:
        separator = "/" if "/" in value else "-"
        parts = [p.strip() for p in value.split(separator) if p.strip()]
        if len(parts) == 3:
            if len(parts[0]) == 4:
                year, month, day = parts[0], parts[1], parts[2]
            else:
                day, month, year = parts[0], parts[1], parts[2]
            return f"{year.zfill(4)}{month.zfill(2)}{day.zfill(2)}"
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) == 8:
        return digits
    raise ValueError("Data de nascimento inválida. Use DD/MM/AAAA ou AAAAMMDD.")


def birth_dates_match(dicom_date: str, user_input: str) -> bool:
    if not dicom_date:
        return False
    try:
        normalized = normalize_birth_date(user_input)
    except ValueError:
        return False
    return dicom_date == normalized


def create_access_token(patient_id: str, patient_name: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": patient_id,
        "name": patient_name,
        "role": "patient",
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada.",
        ) from exc


async def get_current_patient(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária.",
        )
    payload = decode_access_token(credentials.credentials)
    if payload.get("role") != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado.")
    return payload


def create_viewer_token(patient_id: str, study_instance_uid: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.viewer_token_expire_minutes)
    payload = {
        "sub": patient_id,
        "study_uid": study_instance_uid,
        "role": "viewer",
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_viewer_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão de visualização inválida ou expirada.",
        ) from exc
    if payload.get("role") != "viewer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado.")
    return payload


def extract_study_uids_from_uri(uri: str) -> list[str]:
    parsed = urlparse(uri)
    params = parse_qs(parsed.query)
    values = params.get("StudyInstanceUIDs", [])
    uids: list[str] = []
    for value in values:
        uids.extend([part.strip() for part in value.split(",") if part.strip()])
    if not uids:
        match = re.search(r"studies/([^/?]+)", uri)
        if match:
            uids.append(match.group(1))
    return uids


_VIEWER_STATIC_PATH = re.compile(
    r"^/viewer/(?:assets/|app-config\.js|init-service-worker|manifest\.json|sw\.js|.*\.(?:js|css|map|wasm|json|ico|png|svg|woff2?))"
)


def viewer_token_matches_uri(token: str, uri: str) -> bool:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return False
    if payload.get("role") != "viewer":
        return False
    allowed_uid = payload.get("study_uid")
    if not allowed_uid:
        return False

    path = urlparse(uri).path
    if _VIEWER_STATIC_PATH.match(path):
        return True

    requested_uids = extract_study_uids_from_uri(uri)
    if not requested_uids:
        return False
    return allowed_uid in requested_uids
