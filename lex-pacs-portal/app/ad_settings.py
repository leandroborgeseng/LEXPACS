from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from fastapi import HTTPException, status

from .config import settings
from .mwl_sql import _read_raw, _write_raw, utc_now_iso

LEX_CLINICAL_GROUPS = ("radiologista", "tecnico", "admin")

DEFAULT_AD_CONFIG = {
    "enabled": False,
    "connection_url": "ldap://dc01.example.local:389",
    "use_ssl": False,
    "bind_dn": "",
    "bind_password_env": "AD_BIND_PASSWORD",
    "users_dn": "",
    "groups_dn": "",
    "username_ldap_attribute": "sAMAccountName",
    "import_users": True,
    "group_mappings": [
        {"ad_group_cn": "LEX-Radiologistas", "lex_group": "radiologista"},
        {"ad_group_cn": "LEX-Tecnicos", "lex_group": "tecnico"},
        {"ad_group_cn": "LEX-Admins", "lex_group": "admin"},
    ],
    "full_sync_period_hours": 24,
    "changed_sync_period_hours": 1,
}


def _normalize_group_mappings(raw: list[Any] | None) -> list[dict[str, str]]:
    mappings: list[dict[str, str]] = []
    for item in raw or []:
        ad_group_cn = str(item.get("ad_group_cn") or "").strip()
        lex_group = str(item.get("lex_group") or "").strip().lower()
        if not ad_group_cn or lex_group not in LEX_CLINICAL_GROUPS:
            continue
        mappings.append({"ad_group_cn": ad_group_cn, "lex_group": lex_group})
    return mappings


def _normalize_config(cfg: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(DEFAULT_AD_CONFIG)
    out.update(cfg or {})
    out["enabled"] = bool(out.get("enabled"))
    out["use_ssl"] = bool(out.get("use_ssl"))
    out["import_users"] = bool(out.get("import_users", True))
    out["connection_url"] = str(out.get("connection_url") or "").strip()
    out["bind_dn"] = str(out.get("bind_dn") or "").strip()
    out["bind_password_env"] = str(out.get("bind_password_env") or "AD_BIND_PASSWORD").strip()
    out["users_dn"] = str(out.get("users_dn") or "").strip()
    out["groups_dn"] = str(out.get("groups_dn") or "").strip()
    out["username_ldap_attribute"] = (
        str(out.get("username_ldap_attribute") or "sAMAccountName").strip() or "sAMAccountName"
    )
    out["full_sync_period_hours"] = max(1, int(out.get("full_sync_period_hours") or 24))
    out["changed_sync_period_hours"] = max(1, int(out.get("changed_sync_period_hours") or 1))
    out["group_mappings"] = _normalize_group_mappings(out.get("group_mappings"))
    if not out["group_mappings"]:
        out["group_mappings"] = deepcopy(DEFAULT_AD_CONFIG["group_mappings"])
    return out


def get_ad_config() -> dict[str, Any]:
    data = _read_raw()
    cfg = _normalize_config(data.get("ad_ldap") or {})
    import os

    env_name = cfg.get("bind_password_env", "AD_BIND_PASSWORD")
    cfg["bind_password_configured"] = bool(os.environ.get(env_name, ""))
    cfg["keycloak_realm"] = settings.keycloak_realm
    cfg["keycloak_configured"] = bool(settings.keycloak_admin and settings.keycloak_admin_password)
    cfg.pop("bind_password", None)
    return cfg


def save_ad_config(payload: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(payload.get("enabled"))
    connection_url = str(payload.get("connection_url", "")).strip()
    use_ssl = bool(payload.get("use_ssl"))
    bind_dn = str(payload.get("bind_dn", "")).strip()
    bind_password_env = str(payload.get("bind_password_env", "")).strip() or "AD_BIND_PASSWORD"
    users_dn = str(payload.get("users_dn", "")).strip()
    groups_dn = str(payload.get("groups_dn", "")).strip()
    username_attr = str(payload.get("username_ldap_attribute", "sAMAccountName")).strip()
    import_users = bool(payload.get("import_users", True))
    full_sync = max(1, int(payload.get("full_sync_period_hours", 24)))
    changed_sync = max(1, int(payload.get("changed_sync_period_hours", 1)))
    mappings = _normalize_group_mappings(payload.get("group_mappings"))

    if enabled:
        if not connection_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe a URL LDAP do Active Directory.",
            )
        if not bind_dn:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe o Bind DN da conta de serviço.",
            )
        if not users_dn:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe o Users DN (base de usuários no AD).",
            )
        if not groups_dn:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe o Groups DN (base de grupos no AD).",
            )
        if not mappings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Configure ao menos um mapeamento de grupo AD → LEX PACS.",
            )

    data = _read_raw()
    data["ad_ldap"] = _normalize_config(
        {
            "enabled": enabled,
            "connection_url": connection_url,
            "use_ssl": use_ssl,
            "bind_dn": bind_dn,
            "bind_password_env": bind_password_env,
            "users_dn": users_dn,
            "groups_dn": groups_dn,
            "username_ldap_attribute": username_attr,
            "import_users": import_users,
            "group_mappings": mappings,
            "full_sync_period_hours": full_sync,
            "changed_sync_period_hours": changed_sync,
        }
    )
    _write_raw(data)
    return get_ad_config()


def get_ad_sync_meta() -> dict[str, Any]:
    data = _read_raw()
    meta = dict(data.get("ad_sync") or {})
    return {
        "last_at": str(meta.get("last_at") or ""),
        "last_actor": str(meta.get("last_actor") or ""),
        "users_imported": int(meta.get("users_imported") or 0),
        "groups_mapped": int(meta.get("groups_mapped") or 0),
        "memberships_applied": int(meta.get("memberships_applied") or 0),
        "last_error": str(meta.get("last_error") or ""),
        "provider_configured": bool(meta.get("provider_configured")),
        "connection_ok": bool(meta.get("connection_ok")),
    }


def save_ad_sync_meta(**kwargs: Any) -> dict[str, Any]:
    data = _read_raw()
    meta = dict(data.get("ad_sync") or {})
    for key, value in kwargs.items():
        if value is not None:
            meta[key] = value
    data["ad_sync"] = meta
    _write_raw(data)
    return get_ad_sync_meta()


def resolve_bind_password(cfg: dict[str, Any]) -> str:
    import os

    env_name = str(cfg.get("bind_password_env") or "AD_BIND_PASSWORD")
    password = os.environ.get(env_name, "")
    if not password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Senha LDAP não configurada (env {env_name}).",
        )
    return password


def ad_status_payload() -> dict[str, Any]:
    return {
        "config": get_ad_config(),
        "sync": get_ad_sync_meta(),
        "lex_groups": list(LEX_CLINICAL_GROUPS),
    }


def record_ad_sync_success(
    *,
    actor: str,
    users_imported: int,
    groups_mapped: int,
    memberships_applied: int,
) -> dict[str, Any]:
    return save_ad_sync_meta(
        last_at=utc_now_iso(),
        last_actor=actor,
        users_imported=users_imported,
        groups_mapped=groups_mapped,
        memberships_applied=memberships_applied,
        last_error="",
        provider_configured=True,
        connection_ok=True,
    )


def record_ad_sync_error(*, actor: str, error: str) -> dict[str, Any]:
    return save_ad_sync_meta(
        last_at=utc_now_iso(),
        last_actor=actor,
        last_error=error[:500],
        connection_ok=False,
    )
