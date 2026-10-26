"""U2 — cadastro de usuários internos (somente admin)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from . import local_users
from .audit import log_event
from .clinical_auth import require_admin
from .clinical_session import ClinicalUser

router = APIRouter(prefix="/api/admin/users", tags=["users"])


class UserOut(BaseModel):
    username: str
    full_name: str = ""
    profile: str
    active: bool
    must_change_password: bool
    locked: bool
    created_at: str
    created_by: str = ""
    updated_at: str


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    full_name: str = Field(default="", max_length=128)
    profile: str = Field(min_length=1, max_length=16)
    password: str = Field(min_length=1, max_length=256)


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return fwd or (request.client.host if request.client else "")


def _bad(exc: local_users.UserError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("", response_model=list[UserOut])
async def list_all(_: ClinicalUser = Depends(require_admin)) -> list[dict]:
    return local_users.list_users()


@router.get("/profiles")
async def profiles(_: ClinicalUser = Depends(require_admin)) -> dict:
    return {"profiles": list(local_users.INTERNAL_PROFILES)}


@router.post("", response_model=UserOut, status_code=201)
async def create(body: CreateUserRequest, request: Request, admin: ClinicalUser = Depends(require_admin)) -> dict:
    try:
        user = local_users.create_user(
            body.username, body.password, body.profile, full_name=body.full_name, created_by=admin.username
        )
    except local_users.UserError as exc:
        raise _bad(exc) from exc
    log_event("user_create", admin.username, target=user["username"], profile=user["profile"], ip=_ip(request))
    return user


@router.post("/{username}/deactivate", response_model=UserOut)
async def deactivate(username: str, request: Request, admin: ClinicalUser = Depends(require_admin)) -> dict:
    if username.strip().lower() == admin.username:
        raise HTTPException(status_code=400, detail="Você não pode inativar o próprio usuário.")
    try:
        user = local_users.set_active(username, False)
    except local_users.UserError as exc:
        raise _bad(exc) from exc
    log_event("user_deactivate", admin.username, target=user["username"], ip=_ip(request))
    return user


@router.post("/{username}/activate", response_model=UserOut)
async def activate(username: str, request: Request, admin: ClinicalUser = Depends(require_admin)) -> dict:
    try:
        user = local_users.set_active(username, True)
    except local_users.UserError as exc:
        raise _bad(exc) from exc
    log_event("user_activate", admin.username, target=user["username"], ip=_ip(request))
    return user


@router.post("/{username}/reset-password", response_model=UserOut)
async def reset_password(
    username: str, body: ResetPasswordRequest, request: Request, admin: ClinicalUser = Depends(require_admin)
) -> dict:
    try:
        user = local_users.admin_reset_password(username, body.password)
    except local_users.UserError as exc:
        raise _bad(exc) from exc
    log_event("user_reset_password", admin.username, target=user["username"], ip=_ip(request))
    return user
