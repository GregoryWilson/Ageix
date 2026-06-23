from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.architecture_context_service import ArchitectureContextService
from services.architecture_registry_service import ArchitectureRegistryService


def register_capabilities(repo_root: Path):
    def service() -> ArchitectureRegistryService:
        return ArchitectureRegistryService(repo_root)

    def architecture_list(arguments: dict[str, Any]) -> dict[str, Any]:
        result = service().list_nodes(
            project_id=str(arguments.get("project_id") or "") or None,
            node_type=str(arguments.get("node_type") or "") or None,
            parent_id=arguments.get("parent_id"),
        )
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_list"}, "error": None}

    def architecture_details(arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if not identifier:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        node = service().require_node(identifier)
        return {"success": True, "result": node.model_dump(mode="json"), "metadata": {"request_mode": "architecture_details", "architecture_id": node.architecture_id}, "error": None}

    def architecture_children(arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if not identifier:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        result = service().get_children(identifier, include_node=bool(arguments.get("include_node", False)))
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_children"}, "error": None}

    def architecture_subtree(arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if not identifier:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        result = service().get_subtree(identifier)
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_subtree"}, "error": None}


    def architecture_context(arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if not identifier:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        requester = {
            "session_id": str(arguments.get("session_id") or ""),
            "agent_id": str(arguments.get("agent_id") or ""),
            "project_id": str(arguments.get("project_id") or ""),
            "client_id": arguments.get("client_id"),
            "participant_id": arguments.get("participant_id"),
        }
        context = ArchitectureContextService(repo_root).build_context(
            identifier,
            include_detail=bool(arguments.get("include_detail", False)),
            requester_identity=requester,
        )
        return {"success": True, "result": context.model_dump(mode="json"), "metadata": {"request_mode": "architecture_context", "architecture_id": context.architecture_id}, "error": None}

    def architecture_description_draft(arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = str(arguments.get("architecture_id") or arguments.get("path") or "")
        if not identifier:
            return {"success": False, "result": {}, "metadata": {}, "error": "architecture_id_or_path_required"}
        description = ArchitectureContextService(repo_root).create_description(
            identifier,
            purpose=str(arguments.get("purpose") or ""),
            responsibilities=arguments.get("responsibilities") or [],
            boundaries=arguments.get("boundaries") or [],
            open_questions=arguments.get("open_questions") or [],
            detailed_description=str(arguments.get("detailed_description") or ""),
            source_actor=str(arguments.get("source_actor") or "architect_worker"),
            metadata=arguments.get("metadata") or {},
        )
        return {"success": True, "result": description.model_dump(mode="json"), "metadata": {"request_mode": "architecture_description_draft", "description_id": description.description_id}, "error": None}

    def architecture_description_approve(arguments: dict[str, Any]) -> dict[str, Any]:
        description_id = str(arguments.get("description_id") or "")
        if not description_id:
            return {"success": False, "result": {}, "metadata": {}, "error": "description_id_required"}
        description = ArchitectureContextService(repo_root).approve_description(description_id, approved_by=str(arguments.get("approved_by") or "chair"))
        return {"success": True, "result": description.model_dump(mode="json"), "metadata": {"request_mode": "architecture_description_approve", "description_id": description.description_id}, "error": None}

    def architecture_seed_ageix(arguments: dict[str, Any]) -> dict[str, Any]:
        result = service().seed_official_ageix_architecture()
        return {"success": True, "result": result, "metadata": {"request_mode": "architecture_seed_ageix"}, "error": None}

    return [
        (CapabilityDefinition(capability_id="architecture.list", category="architecture", access_level="governed_read", handler="architecture.list", description="List project-scoped architecture hierarchy nodes."), architecture_list),
        (CapabilityDefinition(capability_id="architecture.details", category="architecture", access_level="governed_read", handler="architecture.details", description="Retrieve one architecture node by architecture ID or path."), architecture_details),
        (CapabilityDefinition(capability_id="architecture.children", category="architecture", access_level="governed_read", handler="architecture.children", description="Retrieve direct children for an architecture node."), architecture_children),
        (CapabilityDefinition(capability_id="architecture.subtree", category="architecture", access_level="governed_read", handler="architecture.subtree", description="Retrieve an architecture hierarchy subtree."), architecture_subtree),
        (CapabilityDefinition(capability_id="architecture.context", category="architecture", access_level="governed_read", handler="architecture.context", description="Build summary-first architecture context for a node without repository-wide discovery."), architecture_context),
        (CapabilityDefinition(capability_id="architecture.description.draft", category="architecture", access_level="governed_write", handler="architecture.description.draft", description="Create an ArchitectWorker draft architecture description artifact.", exposed_to_external_agents=False), architecture_description_draft),
        (CapabilityDefinition(capability_id="architecture.description.approve", category="architecture", access_level="governed_write", handler="architecture.description.approve", description="Chair approval for an architecture description artifact.", exposed_to_external_agents=False), architecture_description_approve),
        (CapabilityDefinition(capability_id="architecture.seed_ageix", category="architecture", access_level="governed_write", handler="architecture.seed_ageix", description="Seed the official Ageix project architecture baseline.", exposed_to_external_agents=False), architecture_seed_ageix),
    ]
