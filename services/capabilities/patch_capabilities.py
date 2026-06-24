from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.patch_registry_service import PatchRegistryService
from services.patch_writer_worker import PatchWriterWorker


def register_capabilities(repo_root: Path):
    def registry() -> PatchRegistryService:
        return PatchRegistryService(repo_root)

    def worker() -> PatchWriterWorker:
        return PatchWriterWorker(repo_root)

    def ok(result: dict[str, Any], mode: str) -> dict[str, Any]:
        return {"success": True, "result": result, "metadata": {"request_mode": mode, "repository_target": str(repo_root)}, "error": None}

    def patch_create(arguments: dict[str, Any]) -> dict[str, Any]:
        result = worker().create_patch(
            patch_name=str(arguments.get("patch_name") or "patch.diff"),
            patch_content=str(arguments.get("patch_content") or ""),
            summary=str(arguments.get("summary") or ""),
            project_id=str(arguments.get("project_id") or "Ageix"),
            agent_id=str(arguments.get("agent_id") or "unknown"),
            client_id=str(arguments.get("client_id") or ""),
            session_id=str(arguments.get("session_id") or ""),
            metadata=dict(arguments.get("metadata") or {}),
        )
        return ok(result, "patch_create")

    def patch_list(arguments: dict[str, Any]) -> dict[str, Any]:
        result = registry().list_patches(
            project_id=arguments.get("project_id") if arguments.get("project_id") != "current" else None,
            status=arguments.get("status"),
            validation_status=arguments.get("validation_status"),
            limit=int(arguments.get("limit") or 20),
            offset=int(arguments.get("offset") or 0),
        )
        return ok(result, "patch_list")

    def patch_get(arguments: dict[str, Any]) -> dict[str, Any]:
        result = registry().get_patch(
            str(arguments.get("patch_id") or ""),
            include_content=bool(arguments.get("include_content") or False),
        )
        return ok(result, "patch_get")

    def patch_metadata(arguments: dict[str, Any]) -> dict[str, Any]:
        return ok(registry().metadata(str(arguments.get("patch_id") or "")), "patch_metadata")

    return [
        (CapabilityDefinition(capability_id="patch.create", category="patch", access_level="governed_write", handler="patch.create", description="Store unified diff text as a governed patch artifact without applying it."), patch_create),
        (CapabilityDefinition(capability_id="patch.list", category="patch", access_level="governed_read", handler="patch.list", description="List governed patch packages."), patch_list),
        (CapabilityDefinition(capability_id="patch.get", category="patch", access_level="governed_read", handler="patch.get", description="Retrieve governed patch package metadata and optionally patch content."), patch_get),
        (CapabilityDefinition(capability_id="patch.metadata", category="patch", access_level="governed_read", handler="patch.metadata", description="Retrieve summary-first governed patch metadata."), patch_metadata),
    ]
