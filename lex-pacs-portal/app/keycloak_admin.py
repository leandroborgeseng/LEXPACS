from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import HTTPException, status

from .ad_settings import LEX_CLINICAL_GROUPS, get_ad_config, resolve_bind_password
from .config import settings

logger = logging.getLogger(__name__)

LDAP_PROVIDER_NAME = "lex-active-directory"
GROUP_MAPPER_NAME = "lex-ad-groups"


class KeycloakAdminError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def _admin_base_url() -> str:
    issuer = settings.oidc_issuer_url.rstrip("/")
    marker = "/realms/"
    if marker in issuer:
        return issuer.split(marker, 1)[0]
    return settings.keycloak_admin_base_url.rstrip("/")


def _require_admin_credentials() -> None:
    if not settings.keycloak_admin_user or not settings.keycloak_admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Credenciais do Keycloak Admin não configuradas no portal.",
        )


def _ldap_component_config(cfg: dict[str, Any], bind_password: str) -> dict[str, list[str]]:
    connection_url = str(cfg.get("connection_url") or "")
    if cfg.get("use_ssl") and connection_url.startswith("ldap://"):
        connection_url = "ldaps://" + connection_url[len("ldap://") :]
    full_sync = max(3600, int(cfg.get("full_sync_period_hours") or 24) * 3600)
    changed_sync = max(300, int(cfg.get("changed_sync_period_hours") or 1) * 3600)
    return {
        "enabled": ["true"],
        "vendor": ["ad"],
        "connectionUrl": [connection_url],
        "bindDn": [str(cfg.get("bind_dn") or "")],
        "bindCredential": [bind_password],
        "usersDn": [str(cfg.get("users_dn") or "")],
        "usernameLDAPAttribute": [str(cfg.get("username_ldap_attribute") or "sAMAccountName")],
        "rdnLDAPAttribute": ["cn"],
        "uuidLDAPAttribute": ["objectGUID"],
        "userObjectClasses": ["person, organizationalPerson, user"],
        "connectionPooling": ["true"],
        "pagination": ["true"],
        "batchSizeForSync": ["1000"],
        "fullSyncPeriod": [str(full_sync)],
        "changedSyncPeriod": [str(changed_sync)],
        "importEnabled": ["true" if cfg.get("import_users", True) else "false"],
        "syncRegistrations": ["false"],
        "editMode": ["READ_ONLY"],
        "priority": ["0"],
    }


def _group_mapper_config(groups_dn: str) -> dict[str, list[str]]:
    return {
        "groups.dn": [groups_dn],
        "group.name.ldap.attribute": ["cn"],
        "group.object.classes": ["group"],
        "preserve.group.inheritance": ["false"],
        "ignore.missing.groups": ["true"],
        "membership.ldap.attribute": ["member"],
        "membership.attribute.type": ["DN"],
        "membership.user.ldap.attribute": ["dn"],
        "mode": ["READ_ONLY"],
        "user.roles.retrieve.strategy": ["LOAD_GROUPS_BY_MEMBER_ATTRIBUTE"],
        "memberof.ldap.attribute": ["memberOf"],
        "groups.ldap.filter": ["(objectClass=group)"],
    }


class KeycloakAdminClient:
    def __init__(self) -> None:
        _require_admin_credentials()
        self.base_url = _admin_base_url()
        self.realm = settings.keycloak_realm
        self._token: str | None = None
        self._realm_id: str | None = None

    async def _get_token(self) -> str:
        if self._token:
            return self._token
        token_url = f"{self.base_url}/realms/master/protocol/openid-connect/token"
        data = {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": settings.keycloak_admin_user,
            "password": settings.keycloak_admin_password,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(token_url, data=data)
        if response.status_code >= 400:
            raise KeycloakAdminError(
                "Falha ao autenticar no Keycloak Admin. Verifique KEYCLOAK_ADMIN e KEYCLOAK_ADMIN_PASSWORD.",
                response.status_code,
            )
        payload = response.json()
        token = str(payload.get("access_token") or "")
        if not token:
            raise KeycloakAdminError("Token do Keycloak Admin ausente na resposta.")
        self._token = token
        return token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> httpx.Response:
        token = await self._get_token()
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.request(method, url, headers=headers, params=params, json=json_body)
        if response.status_code == 401:
            self._token = None
            token = await self._get_token()
            headers["Authorization"] = f"Bearer {token}"
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.request(method, url, headers=headers, params=params, json=json_body)
        return response

    async def get_realm_id(self) -> str:
        if self._realm_id:
            return self._realm_id
        response = await self._request("GET", f"/admin/realms/{self.realm}")
        if response.status_code >= 400:
            raise KeycloakAdminError(
                f"Realm Keycloak '{self.realm}' não encontrado.",
                response.status_code,
            )
        payload = response.json()
        realm_id = str(payload.get("id") or "")
        if not realm_id:
            raise KeycloakAdminError("ID do realm Keycloak ausente.")
        self._realm_id = realm_id
        return realm_id

    async def find_ldap_provider(self) -> dict[str, Any] | None:
        realm_id = await self.get_realm_id()
        response = await self._request(
            "GET",
            f"/admin/realms/{self.realm}/components",
            params={
                "parent": realm_id,
                "type": "org.keycloak.storage.UserStorageProvider",
            },
        )
        if response.status_code >= 400:
            raise KeycloakAdminError("Não foi possível listar provedores LDAP.", response.status_code)
        for item in response.json():
            if item.get("providerId") == "ldap" and item.get("name") == LDAP_PROVIDER_NAME:
                return item
        return None

    async def find_group_mapper(self, ldap_provider_id: str) -> dict[str, Any] | None:
        response = await self._request(
            "GET",
            f"/admin/realms/{self.realm}/components",
            params={
                "parent": ldap_provider_id,
                "type": "org.keycloak.storage.ldap.mappers.LDAPStorageMapper",
            },
        )
        if response.status_code >= 400:
            raise KeycloakAdminError("Não foi possível listar mapeadores LDAP.", response.status_code)
        for item in response.json():
            if item.get("providerId") == "group-ldap-mapper" and item.get("name") == GROUP_MAPPER_NAME:
                return item
        return None

    async def upsert_ldap_provider(self, cfg: dict[str, Any], bind_password: str) -> str:
        realm_id = await self.get_realm_id()
        existing = await self.find_ldap_provider()
        body = {
            "name": LDAP_PROVIDER_NAME,
            "providerId": "ldap",
            "providerType": "org.keycloak.storage.UserStorageProvider",
            "parentId": realm_id,
            "config": _ldap_component_config(cfg, bind_password),
        }
        if existing:
            provider_id = str(existing["id"])
            response = await self._request(
                "PUT",
                f"/admin/realms/{self.realm}/components/{provider_id}",
                json_body=body,
            )
        else:
            response = await self._request(
                "POST",
                f"/admin/realms/{self.realm}/components",
                json_body=body,
            )
            if response.status_code >= 400:
                detail = response.text[:300]
                raise KeycloakAdminError(f"Não foi possível criar o provedor LDAP: {detail}", response.status_code)
            location = response.headers.get("location", "")
            provider_id = location.rstrip("/").split("/")[-1] if location else ""
            if not provider_id:
                created = await self.find_ldap_provider()
                provider_id = str(created["id"]) if created else ""
        if not provider_id:
            raise KeycloakAdminError("ID do provedor LDAP não retornado pelo Keycloak.")
        if response.status_code >= 400:
            detail = response.text[:300]
            raise KeycloakAdminError(f"Não foi possível salvar o provedor LDAP: {detail}", response.status_code)

        groups_dn = str(cfg.get("groups_dn") or "")
        mapper = await self.find_group_mapper(provider_id)
        mapper_body = {
            "name": GROUP_MAPPER_NAME,
            "providerId": "group-ldap-mapper",
            "providerType": "org.keycloak.storage.ldap.mappers.LDAPStorageMapper",
            "parentId": provider_id,
            "config": _group_mapper_config(groups_dn),
        }
        if mapper:
            mapper_id = str(mapper["id"])
            mapper_response = await self._request(
                "PUT",
                f"/admin/realms/{self.realm}/components/{mapper_id}",
                json_body=mapper_body,
            )
        else:
            mapper_response = await self._request(
                "POST",
                f"/admin/realms/{self.realm}/components",
                json_body=mapper_body,
            )
        if mapper_response.status_code >= 400:
            detail = mapper_response.text[:300]
            raise KeycloakAdminError(f"Não foi possível salvar o mapeador de grupos: {detail}", mapper_response.status_code)
        return provider_id

    async def test_ldap_connection(self, cfg: dict[str, Any], bind_password: str) -> dict[str, Any]:
        connection_url = str(cfg.get("connection_url") or "")
        if cfg.get("use_ssl") and connection_url.startswith("ldap://"):
            connection_url = "ldaps://" + connection_url[len("ldap://") :]
        body = {
            "action": "testConnection",
            "connectionUrl": connection_url,
            "bindDn": str(cfg.get("bind_dn") or ""),
            "bindCredential": bind_password,
            "useTruststoreSpi": "ldapsOnly" if connection_url.startswith("ldaps://") else "always",
            "connectionTimeout": "5000",
            "authType": "simple",
        }
        response = await self._request("POST", f"/admin/realms/{self.realm}/testLDAPConnection", json_body=body)
        if response.status_code >= 400:
            detail = response.text[:300] or "Conexão LDAP rejeitada."
            raise KeycloakAdminError(detail, response.status_code)
        auth_body = {
            "action": "testAuthentication",
            "connectionUrl": connection_url,
            "bindDn": str(cfg.get("bind_dn") or ""),
            "bindCredential": bind_password,
            "useTruststoreSpi": body["useTruststoreSpi"],
            "connectionTimeout": "5000",
            "authType": "simple",
        }
        auth_response = await self._request(
            "POST",
            f"/admin/realms/{self.realm}/testLDAPConnection",
            json_body=auth_body,
        )
        if auth_response.status_code >= 400:
            detail = auth_response.text[:300] or "Autenticação LDAP falhou."
            raise KeycloakAdminError(detail, auth_response.status_code)
        return {"ok": True, "message": "Conexão e autenticação LDAP OK."}

    async def sync_ldap(self, provider_id: str, action: str) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/admin/realms/{self.realm}/user-storage/{provider_id}/sync",
            params={"action": action},
        )
        if response.status_code >= 400:
            detail = response.text[:300] or "Sincronização LDAP falhou."
            raise KeycloakAdminError(detail, response.status_code)
        payload = response.json() if response.content else {}
        return payload if isinstance(payload, dict) else {"status": "ok"}

    async def list_groups_by_name(self) -> dict[str, dict[str, Any]]:
        response = await self._request("GET", f"/admin/realms/{self.realm}/groups", params={"max": 1000})
        if response.status_code >= 400:
            raise KeycloakAdminError("Não foi possível listar grupos do Keycloak.", response.status_code)

        def walk(groups: list[dict[str, Any]], acc: dict[str, dict[str, Any]]) -> None:
            for group in groups:
                name = str(group.get("name") or "")
                if name:
                    acc[name] = group
                sub = group.get("subGroups") or []
                if isinstance(sub, list):
                    walk(sub, acc)

        indexed: dict[str, dict[str, Any]] = {}
        walk(response.json(), indexed)
        return indexed

    async def get_group_members(self, group_id: str) -> list[dict[str, Any]]:
        response = await self._request(
            "GET",
            f"/admin/realms/{self.realm}/groups/{group_id}/members",
            params={"max": 5000},
        )
        if response.status_code >= 400:
            raise KeycloakAdminError("Não foi possível listar membros do grupo.", response.status_code)
        members = response.json()
        return members if isinstance(members, list) else []

    async def add_user_to_group(self, user_id: str, group_id: str) -> None:
        response = await self._request(
            "PUT",
            f"/admin/realms/{self.realm}/users/{user_id}/groups/{group_id}",
        )
        if response.status_code >= 400:
            detail = response.text[:200]
            raise KeycloakAdminError(f"Falha ao associar usuário ao grupo: {detail}", response.status_code)

    async def apply_lex_group_memberships(self, mappings: list[dict[str, str]]) -> int:
        groups = await self.list_groups_by_name()
        applied = 0
        for mapping in mappings:
            ad_name = mapping["ad_group_cn"]
            lex_name = mapping["lex_group"]
            ad_group = groups.get(ad_name)
            lex_group = groups.get(lex_name)
            if not ad_group or not lex_group:
                logger.warning("Grupo ausente no Keycloak: ad=%s lex=%s", ad_name, lex_name)
                continue
            members = await self.get_group_members(str(ad_group["id"]))
            lex_group_id = str(lex_group["id"])
            for member in members:
                user_id = str(member.get("id") or "")
                if not user_id:
                    continue
                await self.add_user_to_group(user_id, lex_group_id)
                applied += 1
        return applied

    async def count_federated_users(self, provider_id: str) -> int:
        response = await self._request(
            "GET",
            f"/admin/realms/{self.realm}/users",
            params={"max": 1, "briefRepresentation": "true"},
        )
        if response.status_code >= 400:
            return 0
        # Keycloak returns total in header for some versions; fallback count via search
        response = await self._request(
            "GET",
            f"/admin/realms/{self.realm}/users",
            params={"max": 5000, "briefRepresentation": "true"},
        )
        if response.status_code >= 400:
            return 0
        users = response.json()
        if not isinstance(users, list):
            return 0
        return sum(1 for user in users if str(user.get("federationLink") or "") == provider_id)


async def apply_ad_config_to_keycloak(cfg: dict[str, Any] | None = None) -> str:
    config = cfg or get_ad_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Integração AD desabilitada.")
    password = resolve_bind_password(config)
    client = KeycloakAdminClient()
    return await client.upsert_ldap_provider(config, password)


async def test_ad_connection(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    config = cfg or get_ad_config()
    password = resolve_bind_password(config)
    client = KeycloakAdminClient()
    return await client.test_ldap_connection(config, password)


async def sync_ad_users_and_groups(actor: str) -> dict[str, Any]:
    config = get_ad_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Integração AD desabilitada.")
    password = resolve_bind_password(config)
    client = KeycloakAdminClient()
    provider_id = await client.upsert_ldap_provider(config, password)
    users_result = await client.sync_ldap(provider_id, "triggerFullSync")
    groups_result: dict[str, Any] = {}
    try:
        groups_result = await client.sync_ldap(provider_id, "sync-ldap-mappers")
    except KeycloakAdminError as exc:
        logger.warning("Sync de mapeadores LDAP ignorado: %s", exc)
    memberships = await client.apply_lex_group_memberships(config.get("group_mappings") or [])
    users_imported = int(users_result.get("added") or users_result.get("imported") or 0)
    if users_imported == 0:
        users_imported = await client.count_federated_users(provider_id)
    groups_mapped = int(groups_result.get("added") or groups_result.get("updated") or 0)
    if groups_mapped == 0:
        groups_mapped = len(config.get("group_mappings") or [])
    return {
        "provider_id": provider_id,
        "users_imported": users_imported,
        "groups_mapped": groups_mapped,
        "memberships_applied": memberships,
        "users_sync": users_result,
        "groups_sync": groups_result,
        "actor": actor,
    }
