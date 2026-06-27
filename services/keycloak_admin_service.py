from __future__ import annotations

import os
import time
from typing import Any

import requests


class KeycloakAdminError(RuntimeError):
    """Raised when a Keycloak Admin REST API call fails."""


class KeycloakAdminService:
    """Idempotent wrapper around the Keycloak Admin REST API.

    Connection details and admin credentials come from environment variables
    only -- they must never be written to a git-tracked config file such as
    .ageix/config/auth.json.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        realm: str | None = None,
        admin_realm: str | None = None,
        admin_client_id: str | None = None,
        admin_username: str | None = None,
        admin_password: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("KEYCLOAK_BASE_URL") or "http://127.0.0.1:8080").rstrip("/")
        self.realm = realm or os.environ.get("KEYCLOAK_REALM") or "ageix"
        self.admin_realm = admin_realm or os.environ.get("KEYCLOAK_ADMIN_REALM") or "master"
        self.admin_client_id = admin_client_id or os.environ.get("KEYCLOAK_ADMIN_CLIENT_ID") or "admin-cli"
        self.admin_username = admin_username or os.environ.get("KEYCLOAK_ADMIN_USERNAME") or os.environ.get("KEYCLOAK_ADMIN")
        self.admin_password = admin_password or os.environ.get("KEYCLOAK_ADMIN_PASSWORD")
        self.timeout = timeout
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def _admin_token(self) -> str:
        if not self.admin_username or not self.admin_password:
            raise KeycloakAdminError("keycloak_admin_credentials_not_configured")
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        response = requests.post(
            f"{self.base_url}/realms/{self.admin_realm}/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": self.admin_client_id,
                "username": self.admin_username,
                "password": self.admin_password,
            },
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise KeycloakAdminError(f"keycloak_admin_token_request_failed:{response.status_code}")
        payload = response.json()
        self._token = str(payload["access_token"])
        self._token_expires_at = time.monotonic() + max(int(payload.get("expires_in", 60)) - 10, 5)
        return self._token

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url}/admin/realms{path}"
        headers = {"Authorization": f"Bearer {self._admin_token()}", **kwargs.pop("headers", {})}
        response = requests.request(method, url, headers=headers, timeout=self.timeout, **kwargs)
        if response.status_code >= 500:
            raise KeycloakAdminError(f"keycloak_admin_request_failed:{method}:{path}:{response.status_code}")
        return response

    def ensure_realm(self) -> dict[str, Any]:
        existing = self._request("GET", f"/{self.realm}")
        if existing.status_code == 200:
            return existing.json()
        created = self._request("POST", "", json={"realm": self.realm, "enabled": True})
        if created.status_code not in (201, 409):
            raise KeycloakAdminError(f"keycloak_realm_create_failed:{created.status_code}")
        refreshed = self._request("GET", f"/{self.realm}")
        if refreshed.status_code != 200:
            raise KeycloakAdminError(f"keycloak_realm_fetch_failed:{refreshed.status_code}")
        return refreshed.json()

    def find_client_scope(self, name: str) -> dict[str, Any] | None:
        response = self._request("GET", f"/{self.realm}/client-scopes")
        if response.status_code != 200:
            raise KeycloakAdminError(f"keycloak_client_scope_list_failed:{response.status_code}")
        for scope in response.json():
            if scope.get("name") == name:
                return scope
        return None

    def ensure_client_scope(self, name: str) -> dict[str, Any]:
        existing = self.find_client_scope(name)
        if existing is not None:
            return existing
        created = self._request(
            "POST",
            f"/{self.realm}/client-scopes",
            json={
                "name": name,
                "protocol": "openid-connect",
                "attributes": {
                    "include.in.token.scope": "true",
                    "display.on.consent.screen": "false",
                },
            },
        )
        if created.status_code not in (201, 409):
            raise KeycloakAdminError(f"keycloak_client_scope_create_failed:{name}:{created.status_code}")
        refreshed = self.find_client_scope(name)
        if refreshed is None:
            raise KeycloakAdminError(f"keycloak_client_scope_fetch_failed:{name}")
        return refreshed

    def find_client(self, client_id: str) -> dict[str, Any] | None:
        response = self._request("GET", f"/{self.realm}/clients", params={"clientId": client_id})
        if response.status_code != 200:
            raise KeycloakAdminError(f"keycloak_client_list_failed:{response.status_code}")
        matches = response.json()
        return matches[0] if matches else None

    def ensure_client(self, client_id: str) -> dict[str, Any]:
        existing = self.find_client(client_id)
        if existing is not None:
            return existing
        created = self._request(
            "POST",
            f"/{self.realm}/clients",
            json={
                "clientId": client_id,
                "protocol": "openid-connect",
                "publicClient": False,
                "serviceAccountsEnabled": True,
                "standardFlowEnabled": False,
                "implicitFlowEnabled": False,
                "directAccessGrantsEnabled": False,
            },
        )
        if created.status_code not in (201, 409):
            raise KeycloakAdminError(f"keycloak_client_create_failed:{client_id}:{created.status_code}")
        refreshed = self.find_client(client_id)
        if refreshed is None:
            raise KeycloakAdminError(f"keycloak_client_fetch_failed:{client_id}")
        return refreshed

    def ensure_public_pkce_client(self, client_id: str, *, redirect_uris: list[str]) -> dict[str, Any]:
        """Idempotently create or update a public, PKCE-required client for a
        human-delegated authorization_code flow (e.g. a Claude.ai connector) --
        distinct from the confidential service-account clients AI agents use."""
        existing = self.find_client(client_id)
        if existing is not None:
            if set(existing.get("redirectUris") or []) == set(redirect_uris):
                return existing
            response = self._request(
                "PUT",
                f"/{self.realm}/clients/{existing['id']}",
                json={**existing, "redirectUris": redirect_uris},
            )
            if response.status_code not in (204, 409):
                raise KeycloakAdminError(f"keycloak_client_update_failed:{client_id}:{response.status_code}")
            refreshed = self.find_client(client_id)
            if refreshed is None:
                raise KeycloakAdminError(f"keycloak_client_fetch_failed:{client_id}")
            return refreshed

        created = self._request(
            "POST",
            f"/{self.realm}/clients",
            json={
                "clientId": client_id,
                "protocol": "openid-connect",
                "publicClient": True,
                "serviceAccountsEnabled": False,
                "standardFlowEnabled": True,
                "implicitFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "redirectUris": redirect_uris,
                "attributes": {"pkce.code.challenge.method": "S256"},
            },
        )
        if created.status_code not in (201, 409):
            raise KeycloakAdminError(f"keycloak_client_create_failed:{client_id}:{created.status_code}")
        refreshed = self.find_client(client_id)
        if refreshed is None:
            raise KeycloakAdminError(f"keycloak_client_fetch_failed:{client_id}")
        return refreshed

    def get_client_secret(self, client_uuid: str) -> str:
        response = self._request("GET", f"/{self.realm}/clients/{client_uuid}/client-secret")
        if response.status_code != 200:
            raise KeycloakAdminError(f"keycloak_client_secret_fetch_failed:{response.status_code}")
        return str(response.json()["value"])

    def set_default_client_scopes(self, client_uuid: str, scope_names: list[str]) -> None:
        for name in scope_names:
            scope = self.ensure_client_scope(name)
            response = self._request(
                "PUT",
                f"/{self.realm}/clients/{client_uuid}/default-client-scopes/{scope['id']}",
            )
            if response.status_code not in (204, 409):
                raise KeycloakAdminError(f"keycloak_default_scope_assign_failed:{name}:{response.status_code}")

    def find_protocol_mapper(self, client_uuid: str, name: str) -> dict[str, Any] | None:
        response = self._request("GET", f"/{self.realm}/clients/{client_uuid}/protocol-mappers/models")
        if response.status_code != 200:
            raise KeycloakAdminError(f"keycloak_protocol_mapper_list_failed:{response.status_code}")
        for mapper in response.json():
            if mapper.get("name") == name:
                return mapper
        return None

    def ensure_hardcoded_claim_mapper(self, client_uuid: str, *, claim_name: str, claim_value: str) -> dict[str, Any]:
        """Idempotently attach a hardcoded-claim protocol mapper so the client's
        access tokens self-report a stable identity claim (e.g. agent_id) rather
        than relying on a single global default shared by every client."""
        name = f"hardcoded-{claim_name}"
        config = {
            "claim.name": claim_name,
            "claim.value": claim_value,
            "jsonType.label": "String",
            "id.token.claim": "true",
            "access.token.claim": "true",
            "userinfo.token.claim": "true",
        }
        existing = self.find_protocol_mapper(client_uuid, name)
        if existing is not None:
            if existing.get("config", {}).get("claim.value") == claim_value:
                return existing
            response = self._request(
                "PUT",
                f"/{self.realm}/clients/{client_uuid}/protocol-mappers/models/{existing['id']}",
                json={**existing, "config": config},
            )
            if response.status_code not in (204, 409):
                raise KeycloakAdminError(f"keycloak_protocol_mapper_update_failed:{claim_name}:{response.status_code}")
        else:
            created = self._request(
                "POST",
                f"/{self.realm}/clients/{client_uuid}/protocol-mappers/models",
                json={"name": name, "protocol": "openid-connect", "protocolMapper": "oidc-hardcoded-claim-mapper", "config": config},
            )
            if created.status_code not in (201, 409):
                raise KeycloakAdminError(f"keycloak_protocol_mapper_create_failed:{claim_name}:{created.status_code}")
        refreshed = self.find_protocol_mapper(client_uuid, name)
        if refreshed is None:
            raise KeycloakAdminError(f"keycloak_protocol_mapper_fetch_failed:{claim_name}")
        return refreshed
