from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException, status

from .config import settings

CLINICAL_COOKIE_NAME = "lex_clinical_session"
CLINICAL_GROUPS = frozenset({"admin", "radiologista", "tecnico"})


@dataclass
class ClinicalUser:
    username: str
    groups: list[str]
    auth_method: str = "session"

    @property
    def is_admin(self) -> bool:
        return bool({"admin"}.intersection(self.groups))

    @property
    def can_sign(self) -> bool:
        return bool({"radiologista", "admin"}.intersection(self.groups))

    @property
    def can_access_clinical(self) -> bool:
        return bool({"tecnico", "radiologista", "admin"}.intersection(self.groups) or self.groups)


def _filter_clinical_groups(groups: list[str]) -> list[str]:
    return [group for group in groups if group in CLINICAL_GROUPS]


def _normalize_groups(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        return [part.strip().lower() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(item).strip().lower() for item in raw if str(item).strip()]
    return []


def _basic_user_to_groups(username: str) -> list[str]:
    mapping = {
        "clinica": ["radiologista", "admin"],
        "radiologista": ["radiologista"],
        "tecnico": ["tecnico"],
        "admin": ["admin"],
    }
    return mapping.get(username.strip().lower(), ["tecnico"])


def create_clinical_session(username: str, groups: list[str], auth_method: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.clinical_session_hours)
    payload = {
        "sub": username,
        "groups": groups,
        "role": "clinical",
        "auth_method": auth_method,
        "exp": expire,
    }
    import jwt

    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def clinical_user_from_session_token(token: str) -> ClinicalUser | None:
    import jwt

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("role") != "clinical":
        return None
    username = str(payload.get("sub", "")).strip()
    if not username:
        return None
    groups = _normalize_groups(payload.get("groups")) or _basic_user_to_groups(username)
    return ClinicalUser(
        username=username,
        groups=groups,
        auth_method=str(payload.get("auth_method", "session")),
    )


def _verify_htpasswd(username: str, password: str) -> bool:
    from passlib.apache import HtpasswdFile

    path = Path(settings.clinical_htpasswd_path)
    if not path.is_file():
        return False
    try:
        ht = HtpasswdFile(str(path))
        return bool(ht.check_password(username, password))
    except (OSError, ValueError):
        return False


async def _authenticate_keycloak(username: str, password: str) -> ClinicalUser | None:
    if not settings.oidc_enabled:
        return None
    token_url = f"{settings.oidc_issuer_url.rstrip('/')}/protocol/openid-connect/token"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                token_url,
                data={
                    "grant_type": "password",
                    "client_id": settings.oidc_client_id,
                    "client_secret": settings.oidc_client_secret,
                    "username": username,
                    "password": password,
                },
            )
            response.raise_for_status()
            access_token = response.json().get("access_token", "")
    except httpx.HTTPError:
        return None
    if not access_token:
        return None
    try:
        from .clinical_auth import _decode_oidc_token

        claims = _decode_oidc_token(access_token)
    except HTTPException:
        return None
    name = str(claims.get("preferred_username") or claims.get("sub") or username)
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
    return ClinicalUser(username=name, groups=groups, auth_method="oidc")


async def authenticate_clinical(username: str, password: str) -> ClinicalUser:
    username = username.strip()
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos.",
        )

    keycloak_user = await _authenticate_keycloak(username, password)
    if keycloak_user:
        return keycloak_user

    if not settings.clinical_local_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Use login institucional (Keycloak). Autenticação local desabilitada.",
        )

    if _verify_htpasswd(username, password):
        return ClinicalUser(
            username=username,
            groups=_basic_user_to_groups(username),
            auth_method="local",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Usuário ou senha incorretos.",
    )


def session_cookie_kwargs() -> dict[str, Any]:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": settings.cookie_secure,
        "max_age": settings.clinical_session_hours * 3600,
        "path": "/",
    }
