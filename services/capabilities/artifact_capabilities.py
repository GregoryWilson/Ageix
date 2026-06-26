from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.artifact_registry_service import ArtifactRegistryService


def register_capabilities(repo_root: Path):
    def service() -> ArtifactRegistryService:
        return ArtifactRegistryService(repo_root)

    def ok(result: dict[str, Any], mode: str) -> dict[str, Any]:
        return {"success": True, "result": result, "metadata": {"request_mode": mode, "repository_target": str(repo_root)}, "error": None}

    def artifact_list(arguments: dict[str, Any]) -> dict[str, Any]:
        result = service().list_artifacts(
            artifact_category=arguments.get("artifact_category") or arguments.get("category"),
            artifact_type=arguments.get("artifact_type"),
            source_id=arguments.get("source_id"),
            created_by=arguments.get("created_by"),
            project_id=arguments.get("project_id") if arguments.get("project_id") != "current" else None,
            limit=int(arguments.get("limit") or 20),
            offset=int(arguments.get("offset") or 0),
        )
        return ok(result, "artifact_list")

    def artifact_get(arguments: dict[str, Any]) -> dict[str, Any]:
        return ok(service().get_artifact(str(arguments.get("artifact_id") or "")), "artifact_get")

    def artifact_metadata(arguments: dict[str, Any]) -> dict[str, Any]:
        return ok(service().metadata(str(arguments.get("artifact_id") or "")), "artifact_metadata")

    return [
        (CapabilityDefinition(capability_id="artifact.list", category="artifact", access_level="governed_read", handler="artifact.list", description="List governed artifacts with pagination and filters."), artifact_list),
        (CapabilityDefinition(capability_id="artifact.get", category="artifact", access_level="governed_read", handler="artifact.get", description="Retrieve one governed artifact registry record."), artifact_get),
        (CapabilityDefinition(capability_id="artifact.metadata", category="artifact", access_level="governed_read", handler="artifact.metadata", description="Retrieve summary-first artifact metadata and relationships."), artifact_metadata),
    ]
