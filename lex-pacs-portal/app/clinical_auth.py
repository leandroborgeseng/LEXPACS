from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status

from .clinical_session import (
    CLINICAL_COOKIE_NAME,
    ClinicalUser,
    clinical_permissions,  # noqa: F401  (reexportado)
    clinical_user_from_session_token,
)

ADMIN_GROUPS = {"admin"}
RADIOLOGIST_GROUPS = {"medico", "admin"}
TECHNICIAN_GROUPS = {"tecnico", "medico", "admin"}


def _token_from_request(request: Request) -> str:
    session = request.cookies.get(CLINICAL_COOKIE_NAME, "").strip()
    if session:
        return session
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def clinical_user_from_request(request: Request) -> ClinicalUser | None:
    token = _token_from_request(request)
    if not token:
        return None
    return clinical_user_from_session_token(token)


def require_clinical_user_allow_pending(request: Request) -> ClinicalUser:
    """Sessão válida, mesmo com troca de senha pendente (só /me e /change-password)."""
    user = clinical_user_from_request(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação clínica necessária.")
    return user


def require_clinical_user(request: Request) -> ClinicalUser:
    user = require_clinical_user_allow_pending(request)
    if user.must_change_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Troca de senha obrigatória.")
    return user


def require_admin(request: Request) -> ClinicalUser:
    user = require_clinical_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a administradores.")
    return user


def require_can_sign(request: Request) -> ClinicalUser:
    user = require_clinical_user(request)
    if not user.can_sign:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assinatura e liberação restritas a médicos e administradores.",
        )
    return user


def get_optional_clinical_user(request: Request) -> ClinicalUser | None:
    try:
        return clinical_user_from_request(request)
    except HTTPException:
        return None


def auth_public_config() -> dict[str, Any]:
    from .config import settings

    return {"sso_enabled": False, "local_auth": True, "password_min_length": settings.password_min_length}
