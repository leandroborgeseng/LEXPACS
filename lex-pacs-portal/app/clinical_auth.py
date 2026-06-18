from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status

from .config import settings

ADMIN_GROUPS = {"admin"}
RADIOLOGIST_GROUPS = {"radiologista", "admin"}
TECHNICIAN_GROUPS = {"tecnico", "radiologista", "admin"}


@dataclass
class ClinicalUser:
    username: str
    groups: list[str]
    auth_method: str = "basic"

    @property
    def is_admin(self) -> bool:
        return bool(ADMIN_GROUPS.intersection(self.groups))

    @property
    def can_sign(self) -> bool:
        return bool(RADIOLOGIST_GROUPS.intersection(self.groups))

    @property
    def can_access_clinical(self) -> bool:
        return bool(TECHNICIAN_GROUPS.intersection(self.groups) or self.groups)


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
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if not token:
            return None
        try:
            claims = _decode_oidc_token(token)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token OIDC inválido.",
            ) from exc
        username = str(claims.get("preferred_username") or claims.get("sub") or "oidc-user")
        groups = _normalize_groups(claims.get("groups"))
        if not groups:
            realm_roles = claims.get("realm_access", {}).get("roles", [])
            groups = _normalize_groups(realm_roles)
        if not groups:
            groups = _basic_user_to_groups(username)
        return ClinicalUser(username=username, groups=groups, auth_method="oidc")

    clinic_user = request.headers.get("x-clinic-user", "").strip()
    if clinic_user:
        groups_header = request.headers.get("x-clinic-groups", "")
        groups = _normalize_groups(groups_header) or _basic_user_to_groups(clinic_user)
        return ClinicalUser(username=clinic_user, groups=groups, auth_method="basic")

    return None


def require_clinical_user(request: Request) -> ClinicalUser:
    user = clinical_user_from_request(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação clínica necessária.")
    return user


def require_admin(request: Request) -> ClinicalUser:
    user = require_clinical_user(request)
    if settings.oidc_enabled and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a administradores.")
    return user


def get_optional_clinical_user(request: Request) -> ClinicalUser | None:
    try:
        return clinical_user_from_request(request)
    except HTTPException:
        return None


def oidc_status() -> dict[str, Any]:
    return {
        "enabled": settings.oidc_enabled,
        "issuer": settings.oidc_issuer_url if settings.oidc_enabled else "",
        "client_id": settings.oidc_client_id if settings.oidc_enabled else "",
    }
