from __future__ import annotations

from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.capability_definition import CapabilityDefinition
from services.worker_launcher_service import WorkerLauncherService


def register_capabilities(repo_root: Path):
    def service() -> WorkerLauncherService:
        return WorkerLauncherService(repo_root)

    def _actor_id(arguments: dict[str, Any]) -> str:
        return str(arguments.get("actor_id") or arguments.get("client_id") or "")

    def _role(arguments: dict[str, Any]) -> AgentRole:
        return AgentRole.parse(str(arguments.get("agent_role") or ""))

    def launch_artifact_create(arguments: dict[str, Any]) -> dict[str, Any]:
        admission_ticket_id = str(arguments.get("admission_ticket_id") or "")
        adapter = str(arguments.get("adapter") or "")
        if not admission_ticket_id:
            return {"success": False, "result": {}, "error": "admission_ticket_id_required"}
        if not adapter:
            return {"success": False, "result": {}, "error": "adapter_required"}
        try:
            artifact = service().create_launch_artifact(
                admission_ticket_id=admission_ticket_id,
                adapter=adapter,
                worker_profile_id=arguments.get("worker_profile_id"),
                project_id=str(arguments.get("project_id") or "Ageix"),
                requested_by=str(arguments.get("requested_by") or _actor_id(arguments)),
                notes=str(arguments.get("notes") or ""),
                actor_id=_actor_id(arguments),
                actor_role=_role(arguments),
                metadata=arguments.get("metadata") or {},
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": artifact, "metadata": {"source": "worker_launcher_service"}}

    def launch_artifact_get(arguments: dict[str, Any]) -> dict[str, Any]:
        launch_artifact_id = str(arguments.get("launch_artifact_id") or "")
        if not launch_artifact_id:
            return {"success": False, "result": {}, "error": "launch_artifact_id_required"}
        try:
            artifact = service().get_launch_artifact(launch_artifact_id)
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": artifact, "metadata": {"source": "worker_launcher_service"}}

    def launch_artifact_list(arguments: dict[str, Any]) -> dict[str, Any]:
        raw_limit = arguments.get("limit")
        result = service().list_launch_artifacts(
            project_id=arguments.get("project_id"),
            target_id=arguments.get("target_id"),
            limit=int(raw_limit) if raw_limit is not None else 20,
            offset=int(arguments.get("offset") or 0),
        )
        return {"success": True, "result": result, "metadata": {"source": "worker_launcher_service"}}

    return [
        (CapabilityDefinition(
            capability_id="worker.launcher.artifact.create",
            category="worker_launcher",
            access_level="governed_read",
            handler="worker.launcher.artifact.create",
            description="Produce a governed, non-authoritative Claude Code launch handoff artifact from a valid admission ticket and launch profile (Admission Ticket -> Launch Profile -> Launch Artifact). Governance-controlled; performs no execution, per PROP-934ADA8E57B8.",
        ), launch_artifact_create),
        (CapabilityDefinition(
            capability_id="worker.launcher.artifact.get",
            category="worker_launcher",
            access_level="governed_read",
            handler="worker.launcher.artifact.get",
            description="Retrieve a Worker Launcher handoff artifact by ID, including handoff instructions, authority scope, denied actions, and traceability.",
        ), launch_artifact_get),
        (CapabilityDefinition(
            capability_id="worker.launcher.artifact.list",
            category="worker_launcher",
            access_level="governed_read",
            handler="worker.launcher.artifact.list",
            description="List Worker Launcher handoff artifacts with optional project and target filters.",
        ), launch_artifact_list),
    ]
