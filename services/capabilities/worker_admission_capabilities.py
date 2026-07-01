from __future__ import annotations

from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.capability_definition import CapabilityDefinition
from services.worker_admission_service import WorkerAdmissionService


def register_capabilities(repo_root: Path):
    def service() -> WorkerAdmissionService:
        return WorkerAdmissionService(repo_root)

    def _actor_id(arguments: dict[str, Any]) -> str:
        return str(arguments.get("actor_id") or arguments.get("client_id") or "")

    def _role(arguments: dict[str, Any]) -> AgentRole:
        return AgentRole.parse(str(arguments.get("agent_role") or ""))

    def profile_create(arguments: dict[str, Any]) -> dict[str, Any]:
        name = str(arguments.get("name") or "")
        worker_type = str(arguments.get("worker_type") or "")
        if not name:
            return {"success": False, "result": {}, "error": "name_required"}
        if not worker_type:
            return {"success": False, "result": {}, "error": "worker_type_required"}
        created_by = str(arguments.get("created_by") or _actor_id(arguments))
        try:
            profile = service().create_profile(
                name=name,
                worker_type=worker_type,
                permission_mode=str(arguments.get("permission_mode") or "supervised"),
                project_id=str(arguments.get("project_id") or "Ageix"),
                description=str(arguments.get("description") or ""),
                launch_adapter_hint=arguments.get("launch_adapter_hint"),
                created_by=created_by,
                metadata=arguments.get("metadata") or {},
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": profile.to_metadata(), "metadata": {"source": "worker_admission_service"}}

    def profile_list(arguments: dict[str, Any]) -> dict[str, Any]:
        raw_limit = arguments.get("limit")
        result = service().list_profiles(
            project_id=arguments.get("project_id"),
            limit=int(raw_limit) if raw_limit is not None else 20,
            offset=int(arguments.get("offset") or 0),
        )
        return {"success": True, "result": result, "metadata": {"source": "worker_admission_service"}}

    def ticket_create(arguments: dict[str, Any]) -> dict[str, Any]:
        target_id = str(arguments.get("target_id") or "")
        worker_profile_id = str(arguments.get("worker_profile_id") or "")
        if not target_id:
            return {"success": False, "result": {}, "error": "target_id_required"}
        if not worker_profile_id:
            return {"success": False, "result": {}, "error": "worker_profile_id_required"}
        try:
            ticket = service().create_ticket(
                target_type=str(arguments.get("target_type") or "DEVJOB"),
                target_id=target_id,
                worker_profile_id=worker_profile_id,
                permission_mode=arguments.get("permission_mode"),
                required_next_capability=str(arguments.get("required_next_capability") or "devjob.get"),
                project_id=str(arguments.get("project_id") or "Ageix"),
                actor_id=_actor_id(arguments),
                actor_role=_role(arguments),
                metadata=arguments.get("metadata") or {},
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": ticket.to_metadata(), "metadata": {"source": "worker_admission_service"}}

    def ticket_get(arguments: dict[str, Any]) -> dict[str, Any]:
        ticket_id = str(arguments.get("ticket_id") or "")
        if not ticket_id:
            return {"success": False, "result": {}, "error": "ticket_id_required"}
        try:
            ticket = service().get_ticket(ticket_id)
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": ticket.to_metadata(), "metadata": {"source": "worker_admission_service"}}

    def ticket_redeem(arguments: dict[str, Any]) -> dict[str, Any]:
        ticket_id = str(arguments.get("ticket_id") or "")
        if not ticket_id:
            return {"success": False, "result": {}, "error": "ticket_id_required"}
        worker_id = str(arguments.get("worker_id") or _actor_id(arguments))
        try:
            admission = service().redeem_ticket(
                ticket_id=ticket_id,
                worker_id=worker_id,
                actor_role=_role(arguments),
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": admission, "metadata": {"source": "worker_admission_service"}}

    def ticket_revive(arguments: dict[str, Any]) -> dict[str, Any]:
        ticket_id = str(arguments.get("ticket_id") or "")
        if not ticket_id:
            return {"success": False, "result": {}, "error": "ticket_id_required"}
        try:
            ticket = service().revive_ticket(
                ticket_id=ticket_id,
                actor_id=_actor_id(arguments),
                actor_role=_role(arguments),
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": ticket.to_metadata(), "metadata": {"source": "worker_admission_service"}}

    return [
        (CapabilityDefinition(
            capability_id="worker.admission.profile.create",
            category="worker_admission",
            access_level="governed_read",
            handler="worker.admission.profile.create",
            description="Create a governed WorkerLaunchProfile describing how a class of worker is admitted (permission mode, transport hint). Grants no authority, per ADR-0014.",
        ), profile_create),
        (CapabilityDefinition(
            capability_id="worker.admission.profile.list",
            category="worker_admission",
            access_level="governed_read",
            handler="worker.admission.profile.list",
            description="List governed WorkerLaunchProfiles.",
        ), profile_list),
        (CapabilityDefinition(
            capability_id="worker.admission.ticket.create",
            category="worker_admission",
            access_level="governed_read",
            handler="worker.admission.ticket.create",
            description="Issue a scoped, single-use, time-limited Worker Admission ticket for a DEVJOB-* target. Governance-controlled; grants participation, never authority, per ADR-0014.",
        ), ticket_create),
        (CapabilityDefinition(
            capability_id="worker.admission.ticket.get",
            category="worker_admission",
            access_level="governed_read",
            handler="worker.admission.ticket.get",
            description="Retrieve a Worker Admission ticket by ID, including lifecycle and status.",
        ), ticket_get),
        (CapabilityDefinition(
            capability_id="worker.admission.ticket.redeem",
            category="worker_admission",
            access_level="governed_read",
            handler="worker.admission.ticket.redeem",
            description="Redeem a Worker Admission ticket, returning minimal admission context only. Never returns the DevJob and never bypasses assignment or governance, per ADR-0014.",
        ), ticket_redeem),
        (CapabilityDefinition(
            capability_id="worker.admission.ticket.revive",
            category="worker_admission",
            access_level="governed_read",
            handler="worker.admission.ticket.revive",
            description="Duplicate a stale Worker Admission ticket into a fresh, traceable ticket. Governance-controlled, per ADR-0014.",
        ), ticket_revive),
    ]
