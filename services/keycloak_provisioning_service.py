from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ageix_mcp.clients.client_registry import MCPClientRegistry
from services.capability_registry_service import CapabilityRegistryService
from services.keycloak_admin_service import KeycloakAdminService

CAPABILITY_SCOPE_PREFIX = "ageix.capability:"
PROJECT_SCOPE_PREFIX = "ageix.project:"


@dataclass(frozen=True)
class ProvisioningResult:
    client_id: str
    skipped: bool
    reason: str
    keycloak_client_id: str | None = None
    keycloak_client_uuid: str | None = None
    scope_names: list[str] = field(default_factory=list)
    secret_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "skipped": self.skipped,
            "reason": self.reason,
            "keycloak_client_id": self.keycloak_client_id,
            "keycloak_client_uuid": self.keycloak_client_uuid,
            "scope_names": self.scope_names,
            "secret_path": self.secret_path,
        }


class KeycloakProvisioningService:
    """Automates Keycloak client/scope provisioning for registered MCP clients.

    Triggered by MCP client registration rather than per-action approval --
    callers must already hold the internal "chair" authority, so this is
    Greg's standing authorization expressed through the existing governance
    model rather than a manual click-through per client.
    """

    def __init__(
        self,
        repo_root: str | Path = ".",
        *,
        admin: KeycloakAdminService | None = None,
        client_registry: MCPClientRegistry | None = None,
        capability_registry: CapabilityRegistryService | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.admin = admin or KeycloakAdminService()
        self.client_registry = client_registry or MCPClientRegistry()
        self.capability_registry = capability_registry or CapabilityRegistryService(self.repo_root)

    def provision_client(self, client_id: str) -> ProvisioningResult:
        definition = self.client_registry.get(client_id)
        if definition is None:
            return ProvisioningResult(client_id=client_id, skipped=True, reason="mcp_client_not_registered")
        if definition.placeholder or not definition.enabled:
            return ProvisioningResult(client_id=client_id, skipped=True, reason="mcp_client_disabled_or_placeholder")

        capability_scopes, project_scopes = self._scopes_for(definition.client_id)
        keycloak_client_id = f"ageix-mcp-{definition.client_id.lower()}"

        self.admin.ensure_realm()
        client = self.admin.ensure_client(keycloak_client_id)
        secret = self.admin.get_client_secret(client["id"])
        scope_names = [f"{CAPABILITY_SCOPE_PREFIX}{cap}" for cap in capability_scopes] + [
            f"{PROJECT_SCOPE_PREFIX}{proj}" for proj in project_scopes
        ]
        self.admin.set_default_client_scopes(client["id"], scope_names)
        secret_path = self._persist_secret(definition.client_id, keycloak_client_id, client["id"], secret)

        return ProvisioningResult(
            client_id=definition.client_id,
            skipped=False,
            reason="provisioned",
            keycloak_client_id=keycloak_client_id,
            keycloak_client_uuid=client["id"],
            scope_names=scope_names,
            secret_path=str(secret_path),
        )

    def reconcile_all(self) -> list[ProvisioningResult]:
        clients = self.client_registry.list_clients(include_placeholders=False, include_disabled=False)
        return [self.provision_client(str(client["client_id"])) for client in clients]

    def _scopes_for(self, client_id: str) -> tuple[list[str], list[str]]:
        config = self._load_auth_config()
        oauth = config.get("jwt") or config.get("oauth") or {}
        allowed_capabilities = list(oauth.get("default_allowed_capabilities") or [])
        allowed_projects = list(oauth.get("default_allowed_projects") or config.get("allowed_projects") or [])

        if "*" in allowed_capabilities:
            allowed_capabilities = [
                cap.capability_id
                for cap in self.capability_registry.list_capabilities()
                if cap.exposed_to_external_agents
            ]
        return allowed_capabilities, allowed_projects

    def _load_auth_config(self) -> dict[str, Any]:
        path = self.repo_root / ".ageix" / "config" / "auth.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _persist_secret(self, client_id: str, keycloak_client_id: str, keycloak_client_uuid: str, secret: str) -> Path:
        directory = self.repo_root / ".ageix" / "instance" / "keycloak"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{client_id}.json"
        path.write_text(
            json.dumps(
                {
                    "client_id": client_id,
                    "keycloak_client_id": keycloak_client_id,
                    "keycloak_client_uuid": keycloak_client_uuid,
                    "client_secret": secret,
                    "provisioned_at": int(time.time()),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        path.chmod(0o600)
        return path
