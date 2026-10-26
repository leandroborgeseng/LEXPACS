"""Sessão clínica com usuários locais (sem Keycloak/OIDC).

O cookie/Bearer é um JWT HS256 com `sid`; a sessão real vive no banco local
(`local_users.sessions`) e expira por inatividade (SESSION_IDLE_MINUTES).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, status

from . import local_users
from .config import settings

CLINICAL_COOKIE_NAME = "lex_clinical_session"
CLINICAL_GROUPS = frozenset(local_users.INTERNAL_PROFILES)

ROLE_LABELS = {
    "admin": "Administrador",
    "medico": "Médico",
    "tecnico": "Técnico",
    "recepcao": "Recepção",
    "paciente": "Paciente",
}


@dataclass
class ClinicalUser:
    username: str
    groups: list[str] = field(default_factory=list)
    auth_method: str = "local"
    must_change_password: bool = False
    sid: str = ""

    @property
    def profile(self) -> str:
        return self.groups[0] if self.groups else ""

    @property
    def is_admin(self) -> bool:
        return "admin" in self.groups

    @property
    def can_sign(self) -> bool:
        return bool({"medico", "admin"}.intersection(self.groups))

    @property
    def can_view_images(self) -> bool:
        return bool({"admin", "medico", "tecnico"}.intersection(self.groups))

    @property
    def can_access_clinical(self) -> bool:
        return bool(CLINICAL_GROUPS.intersection(self.groups))


def clinical_permissions(user: ClinicalUser) -> dict[str, Any]:
    role = user.profile or "tecnico"
    return {
        "is_admin": user.is_admin,
        "can_sign": user.can_sign,
        "can_draft": user.can_sign or "tecnico" in user.groups,
        "can_release": user.can_sign,
        "can_admin": user.is_admin,
        "can_view_images": user.can_view_images,
        "must_change_password": user.must_change_password,
        "role": role,
        "role_label": ROLE_LABELS.get(role, role),
    }


def create_clinical_session(user: ClinicalUser) -> str:
    sid = local_users.create_session(user.username)
    user.sid = sid
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.clinical_session_hours)
    payload = {"sub": user.username, "sid": sid, "role": "clinical", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("role") != "clinical" or not payload.get("sid"):
        return None
    return payload


def clinical_user_from_session_token(token: str) -> ClinicalUser | None:
    payload = _decode(token)
    if not payload:
        return None
    record = local_users.touch_session(str(payload["sid"]))
    if not record or record["username"] != str(payload.get("sub", "")).lower():
        return None
    if record["profile"] not in CLINICAL_GROUPS:
        return None
    return ClinicalUser(
        username=record["username"],
        groups=[record["profile"]],
        auth_method="local",
        must_change_password=record["must_change_password"],
        sid=str(payload["sid"]),
    )


def end_session(token: str) -> None:
    payload = _decode(token)
    if payload:
        local_users.delete_session(str(payload["sid"]))


_LOGIN_ERRORS = {
    "invalid": (status.HTTP_401_UNAUTHORIZED, "Usuário ou senha incorretos."),
    "inactive": (status.HTTP_401_UNAUTHORIZED, "Usuário ou senha incorretos."),
    "locked": (
        status.HTTP_423_LOCKED,
        "Conta bloqueada temporariamente por tentativas inválidas. Tente novamente mais tarde.",
    ),
}


async def authenticate_clinical(username: str, password: str) -> ClinicalUser:
    username = (username or "").strip()
    if not username or not password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário ou senha incorretos.")
    result = local_users.verify_login(username, password)
    if not result.ok or not result.user:
        code, detail = _LOGIN_ERRORS.get(result.reason, _LOGIN_ERRORS["invalid"])
        raise HTTPException(status_code=code, detail=detail)
    if result.user["profile"] not in CLINICAL_GROUPS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Perfil sem acesso à área clínica.")
    return ClinicalUser(
        username=result.user["username"],
        groups=[result.user["profile"]],
        auth_method="local",
        must_change_password=result.user["must_change_password"],
    )


def session_cookie_kwargs() -> dict[str, Any]:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": settings.cookie_secure,
        "max_age": settings.clinical_session_hours * 3600,
        "path": "/",
    }
