from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status

from .config import settings
from .clinical_session import (
    CLINICAL_COOKIE_NAME,
    ClinicalUser,
    _basic_user_to_groups,
    _filter_clinical_groups,
    _normalize_groups,
    clinical_user_from_session_token,
)
from .clinical_oidc import clinical_permissions, oidc_public_config

ADMIN_GROUPS = {"admin"}
RADIOLOGIST_GROUPS = {"radiologista", "admin"}
TECHNICIAN_GROUPS = {"tecnico", "radiologista", "admin"}


def _decode_oidc_token(token: str) -> dict[str, Any]:
    import jwt
    from jwt import PyJWKClient

    if not settings.oidc_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC desabilitado.")
    jwks_url = f"{settings.oidc_issuer_url.rstrip('/')}/protocol/openid-connect/certs"
    jwk_client = PyJWKClient(jwks_url)
    signing_key = jwk_client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        options={"verify_aud": False},
    )
    azp = str(claims.get("azp", ""))
    audience = claims.get("aud", [])
    if isinstance(audience, str):
        audience = [audience]
    if azp != settings.oidc_client_id and settings.oidc_client_id not in audience:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token OIDC emitido para outro client.",
        )
    return claims


def clinical_user_from_request(request: Request) -> ClinicalUser | None:
    session = request.cookies.get(CLINICAL_COOKIE_NAME, "").strip()
    if session:
        user = clinical_user_from_session_token(session)
        if user:
            return user

    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if not token:
            return None
        user = clinical_user_from_session_token(token)
        if user:
            return user
        try:
            claims = _decode_oidc_token(token)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token OIDC inválido.",
            ) from exc
        username = str(claims.get("preferred_username") or claims.get("sub") or "oidc-user")
        groups = _filter_clinical_groups(_normalize_groups(claims.get("groups")))
        if not groups:
            groups = _filter_clinical_groups(
                _normalize_groups(claims.get("realm_access", {}).get("roles", []))
            )
        if not groups:
            groups = _filter_clinical_groups(_basic_user_to_groups(username))
        return ClinicalUser(username=username, groups=groups, auth_method="oidc")

    return None


def require_clinical_user(request: Request) -> ClinicalUser:
    user = clinical_user_from_request(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação clínica necessária.")
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
            detail="Assinatura e liberação restritas a radiologistas e administradores.",
        )
    return user


def get_optional_clinical_user(request: Request) -> ClinicalUser | None:
    try:
        return clinical_user_from_request(request)
    except HTTPException:
        return None


def oidc_status() -> dict[str, Any]:
    return oidc_public_config()
