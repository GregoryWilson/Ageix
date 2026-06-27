from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class OAuthDiscoveryService:
    """Build OAuth/OIDC metadata for ChatGPT MCP connector discovery."""

    DEFAULT_AUTH_PATH = "/.ageix/config/auth.json"

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.config_path = self.repo_root / ".ageix" / "config" / "auth.json"
        self.config = self._load_config()
        self.jwt_config = dict(self.config.get("jwt") or self.config.get("oauth") or {})

    def protected_resource_metadata(self, resource_url: str) -> dict[str, Any]:
        issuer = self.issuer
        scopes = self.supported_scopes()
        return {
            "resource": resource_url.rstrip("/"),
            "authorization_servers": [issuer] if issuer else [],
            "bearer_methods_supported": ["header"],
            "scopes_supported": scopes,
            "resource_documentation": f"{resource_url.rstrip('/')}/tools" if resource_url else None,
        }

    def authorization_server_metadata(self, base_url: str) -> dict[str, Any]:
        issuer = self.issuer
        auth_endpoint = self.jwt_config.get("authorization_endpoint") or self._kc("/protocol/openid-connect/auth")
        token_endpoint = self.jwt_config.get("token_endpoint") or self._kc("/protocol/openid-connect/token")
        jwks_uri = self.jwt_config.get("jwks_uri") or self._kc("/protocol/openid-connect/certs")
        userinfo_endpoint = self.jwt_config.get("userinfo_endpoint") or self._kc("/protocol/openid-connect/userinfo")
        registration_endpoint = self.jwt_config.get("registration_endpoint") or self._kc("/clients-registrations/openid-connect")
        return {
            "issuer": issuer,
            "authorization_endpoint": auth_endpoint,
            "token_endpoint": token_endpoint,
            "jwks_uri": jwks_uri,
            "userinfo_endpoint": userinfo_endpoint,
            "registration_endpoint": registration_endpoint,
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "none"],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": self.supported_scopes(),
        }

    def openid_configuration(self, base_url: str) -> dict[str, Any]:
        metadata = self.authorization_server_metadata(base_url)
        metadata.update({
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": list(self.jwt_config.get("algorithms") or ["RS256"]),
            "claims_supported": ["sub", "iss", "aud", "exp", "iat", "preferred_username", "email", "scope", "azp"],
        })
        return metadata

    @property
    def issuer(self) -> str:
        return str(self.jwt_config.get("issuer") or "").rstrip("/")

    def supported_scopes(self) -> list[str]:
        configured = list(self.jwt_config.get("scopes_supported") or self.config.get("scopes_supported") or [])
        capabilities = list(self.jwt_config.get("default_allowed_capabilities") or [])
        projects = list(self.jwt_config.get("default_allowed_projects") or [])
        capability_prefix = str(self.jwt_config.get("capability_scope_prefix") or "ageix.capability:")
        project_prefix = str(self.jwt_config.get("project_scope_prefix") or "ageix.project:")
        derived = ["openid", "profile", "email"]
        derived.extend(f"{capability_prefix}{item}" for item in capabilities if item != "*")
        derived.extend(f"{project_prefix}{item}" for item in projects if item != "*")
        return _dedupe(configured + derived)

    def _kc(self, suffix: str) -> str | None:
        return f"{self.issuer}{suffix}" if self.issuer else None

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        return json.loads(self.config_path.read_text(encoding="utf-8"))


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result
