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

    def keycloak_provision_connector(arguments: dict[str, Any]) -> dict[str, Any]:
        connector_id = str(arguments.get("connector_id") or "")
        redirect_uris = [str(uri) for uri in (arguments.get("redirect_uris") or [])]
        if not connector_id:
            return {"success": False, "result": {}, "error": "connector_id_required"}
        if not redirect_uris:
            return {"success": False, "result": {}, "error": "redirect_uris_required"}
        result = KeycloakProvisioningService(repo_root).provision_connector_client(connector_id, redirect_uris)
        return {
            "success": not result.skipped,
            "result": result.to_dict(),
            "metadata": {"source": "keycloak_provisioning"},
        }

    def keycloak_enable_connector_self_registration(arguments: dict[str, Any]) -> dict[str, Any]:
        trusted_hosts = [str(host) for host in (arguments.get("trusted_hosts") or [])]
        max_clients = int(arguments.get("max_clients") or 1)
        if not trusted_hosts:
            return {"success": False, "result": {}, "error": "trusted_hosts_required"}
        result = KeycloakProvisioningService(repo_root).enable_connector_self_registration(trusted_hosts, max_clients=max_clients)
        return {
            "success": True,
            "result": result,
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
        (
            CapabilityDefinition(
                capability_id="identity.keycloak.connector.provision",
                category="identity",
                access_level="governed_write",
                handler="identity.keycloak.connector.provision",
                description="Provision (or re-provision) a public, PKCE-required Keycloak client for a human-delegated OAuth connector (e.g. Claude.ai).",
                exposed_to_external_agents=False,
            ),
            keycloak_provision_connector,
        ),
        (
            CapabilityDefinition(
                capability_id="identity.keycloak.connector.enable_self_registration",
                category="identity",
                access_level="governed_write",
                handler="identity.keycloak.connector.enable_self_registration",
                description="Enable RFC 7591 anonymous Dynamic Client Registration for this realm, gated to a set of trusted redirect-URI hosts, so a human-delegated connector (e.g. Claude.ai) can self-register a public PKCE client.",
                exposed_to_external_agents=False,
            ),
            keycloak_enable_connector_self_registration,
        ),
    ]
