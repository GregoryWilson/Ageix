from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.artifact_delivery_service import ArtifactDeliveryService


def register_capabilities(repo_root: Path):
    def service() -> ArtifactDeliveryService:
        return ArtifactDeliveryService(repo_root)

    def ok(result: dict[str, Any], mode: str) -> dict[str, Any]:
        return {"success": True, "result": result, "metadata": {"request_mode": mode, "repository_target": str(repo_root)}, "error": None}

    def artifact_push(arguments: dict[str, Any]) -> dict[str, Any]:
        result = service().push(
            artifact_id=str(arguments.get("artifact_id") or ""),
            destination=str(arguments.get("destination") or "requesting_agent"),
            project_id=str(arguments.get("project_id") or "Ageix"),
            agent_id=str(arguments.get("agent_id") or ""),
            client_id=str(arguments.get("client_id") or ""),
            provider=str(arguments.get("provider") or ""),
            client_context=dict(arguments.get("client_context") or {}),
        )
        return ok(result, "artifact_push")

    def delivery_get(arguments: dict[str, Any]) -> dict[str, Any]:
        return ok(
            service().get_delivery(
                str(arguments.get("delivery_id") or ""),
                include_reference=bool(arguments.get("include_reference") or False),
            ),
            "artifact_delivery_get",
        )

    def delivery_list(arguments: dict[str, Any]) -> dict[str, Any]:
        result = service().list_deliveries(
            artifact_id=arguments.get("artifact_id"),
            destination=arguments.get("destination"),
            status=arguments.get("status"),
            project_id=arguments.get("project_id") if arguments.get("project_id") != "current" else None,
            limit=int(arguments.get("limit") or 20),
            offset=int(arguments.get("offset") or 0),
        )
        return ok(result, "artifact_delivery_list")

    return [
        (CapabilityDefinition(capability_id="artifact.push", category="artifact_delivery", access_level="governed_read", handler="artifact.push", description="Deliver an existing governed artifact to an approved destination or the authenticated requesting agent."), artifact_push),
        (CapabilityDefinition(capability_id="artifact.delivery.get", category="artifact_delivery", access_level="governed_read", handler="artifact.delivery.get", description="Retrieve one artifact delivery record."), delivery_get),
        (CapabilityDefinition(capability_id="artifact.delivery.list", category="artifact_delivery", access_level="governed_read", handler="artifact.delivery.list", description="List artifact delivery records with pagination and filters."), delivery_list),
    ]
