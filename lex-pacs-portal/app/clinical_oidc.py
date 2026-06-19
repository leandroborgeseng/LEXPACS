from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status

from .clinical_session import ClinicalUser, _filter_clinical_groups, _normalize_groups
from .config import settings

ROLE_LABELS = {
    "admin": "Administrador",
    "radiologista": "Radiologista",
    "tecnico": "Técnico",
    "clinico": "Clínico",
}


def primary_role(groups: list[str]) -> str:
    if "admin" in groups:
        return "admin"
    if "radiologista" in groups:
        return "radiologista"
    if "tecnico" in groups:
        return "tecnico"
    return "clinico"


def clinical_permissions(user: ClinicalUser) -> dict[str, Any]:
    role = primary_role(user.groups)
    return {
        "is_admin": user.is_admin,
        "can_sign": user.can_sign,
        "can_draft": user.can_access_clinical,
        "can_release": user.can_sign,
        "can_admin": user.is_admin,
        "role": role,
        "role_label": ROLE_LABELS.get(role, "Clínico"),
    }


def oidc_public_config() -> dict[str, Any]:
    issuer = settings.oidc_public_issuer_url.rstrip("/") if settings.oidc_enabled else ""
    redirect_uri = ""
    login_url = ""
    if settings.oidc_enabled and issuer:
        redirect_uri = settings.oidc_redirect_uri
        params = urlencode(
            {
                "client_id": settings.oidc_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid profile email",
            }
        )
        login_url = f"{issuer}/protocol/openid-connect/auth?{params}"
    return {
        "enabled": settings.oidc_enabled,
        "issuer": settings.oidc_issuer_url if settings.oidc_enabled else "",
        "public_issuer": issuer,
        "client_id": settings.oidc_client_id if settings.oidc_enabled else "",
        "redirect_uri": redirect_uri,
        "login_url_template": login_url,
        "local_auth_enabled": settings.clinical_local_auth_enabled,
        "login_mode": "keycloak" if settings.oidc_enabled else "local",
    }


def create_oidc_state(next_path: str) -> str:
    import jwt

    payload = {
        "next": next_path if next_path.startswith("/") and not next_path.startswith("//") else "/viewer/",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        "purpose": "oidc_login",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def parse_oidc_state(state: str) -> str:
    import jwt

    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="State OIDC inválido.") from exc
    if payload.get("purpose") != "oidc_login":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="State OIDC inválido.")
    next_path = str(payload.get("next") or "/viewer/")
    if not next_path.startswith("/") or next_path.startswith("//"):
        return "/viewer/"
    return next_path


def oidc_authorize_url(next_path: str) -> str:
    if not settings.oidc_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OIDC desabilitado.")
    state = create_oidc_state(next_path)
    redirect_uri = settings.oidc_redirect_uri
    issuer = settings.oidc_public_issuer_url.rstrip("/")
    params = urlencode(
        {
            "client_id": settings.oidc_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid profile email",
            "state": state,
        }
    )
    return f"{issuer}/protocol/openid-connect/auth?{params}"


async def exchange_oidc_code(code: str) -> ClinicalUser:
    if not settings.oidc_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OIDC desabilitado.")
    token_url = f"{settings.oidc_issuer_url.rstrip('/')}/protocol/openid-connect/token"
    redirect_uri = settings.oidc_redirect_uri
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.oidc_client_id,
                    "client_secret": settings.oidc_client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            response.raise_for_status()
            access_token = response.json().get("access_token", "")
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falha ao trocar código OIDC.",
        ) from exc
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token OIDC ausente.")
    from .clinical_auth import _decode_oidc_token

    claims = _decode_oidc_token(access_token)
    username = str(claims.get("preferred_username") or claims.get("sub") or "oidc-user")
    groups = _filter_clinical_groups(_normalize_groups(claims.get("groups")))
    if not groups:
        groups = _filter_clinical_groups(
            _normalize_groups(claims.get("realm_access", {}).get("roles", []))
        )
    if not groups:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário sem perfil clínico (admin, radiologista ou técnico).",
        )
    return ClinicalUser(username=username, groups=groups, auth_method="oidc")
