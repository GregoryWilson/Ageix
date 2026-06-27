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
        self.admin_username = admin_username or os.environ.get("KEYCLOAK_ADMIN_USERNAME")
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
