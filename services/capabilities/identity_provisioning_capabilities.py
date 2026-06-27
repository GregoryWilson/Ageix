from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.keycloak_provisioning_service import KeycloakProvisioningService


def register_capabilities(repo_root: Path):
    def keycloak_reconcile(arguments: dict[str, Any]) -> dict[str, Any]:
        results = KeycloakProvisioningService(repo_root).reconcile_all()
        return {
            "success": True,
            "result": {"clients": [item.to_dict() for item in results]},
            "metadata": {"source": "keycloak_provisioning", "provisioned": sum(1 for item in results if not item.skipped)},
        }

    def keycloak_provision_client(arguments: dict[str, Any]) -> dict[str, Any]:
        client_id = str(arguments.get("mcp_client_id") or arguments.get("client_id") or "")
        if not client_id:
            return {"success": False, "result": {}, "error": "mcp_client_id_required"}
        result = KeycloakProvisioningService(repo_root).provision_client(client_id)
        return {
            "success": not result.skipped,
            "result": result.to_dict(),
            "metadata": {"source": "keycloak_provisioning"},
        }

    return [
        (
            CapabilityDefinition(
                capability_id="identity.keycloak.reconcile",
                category="identity",
                access_level="governed_write",
                handler="identity.keycloak.reconcile",
                description="Reconcile Keycloak realm clients/scopes against the registered MCP client list.",
                exposed_to_external_agents=False,
            ),
            keycloak_reconcile,
        ),
        (
            CapabilityDefinition(
                capability_id="identity.keycloak.client.provision",
                category="identity",
                access_level="governed_write",
                handler="identity.keycloak.client.provision",
                description="Provision (or re-provision) the Keycloak client for a single registered MCP client.",
                exposed_to_external_agents=False,
            ),
            keycloak_provision_client,
        ),
    ]
