from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.controls_service import ControlsService
from services.capability_audit_service import CapabilityAuditService


def register_capabilities(repo_root: Path):
    def health(arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "result": {"status": "ok", "system": "ageix", "capability_interface": "available"},
            "metadata": {"source": "ageix"},
        }

    def audit_recent(arguments: dict[str, Any]) -> dict[str, Any]:
        session_id = str(arguments.get("session_id") or "")
        agent_id = str(arguments.get("agent_id") or "")
        limit = int(arguments.get("limit") or 20)
        records = CapabilityAuditService(repo_root).list_records()
        scoped = [record for record in records if (session_id and record.get("session_id") == session_id) or (agent_id and record.get("agent_id") == agent_id)]
        return {"success": True, "result": {"records": scoped[-limit:]}, "metadata": {"source": "capability_audit"}}

    def governance_status(arguments: dict[str, Any]) -> dict[str, Any]:
        controls = ControlsService(repo_root).get_raw_config()
        return {
            "success": True,
            "result": {
                "external_agent_access": "governed",
                "raw_repository_access": "denied",
                "governed_repository_evidence": "available_by_proposal",
                "worker_direct_execution": "denied",
                "promotion_direct_execution": "denied",
                "evidence_broker_required": True,
                "target_resolution_required": True,
                "chair_approval_required": True,
                "audit_required": True,
                "human_override_available": True,
                "agent_capability_controls": controls.get("agent_capabilities", {}),
            },
            "metadata": {"source": "controls"},
        }

    return [
        (CapabilityDefinition(
            capability_id="ageix.health",
            category="system",
            access_level="read",
            handler="system.health",
            description="Return Ageix capability interface health.",
        ), health),
        (CapabilityDefinition(
            capability_id="audit.recent",
            category="audit",
            access_level="read",
            handler="system.audit_recent",
            description="Return recent scoped external-agent audit records.",
        ), audit_recent),
        (CapabilityDefinition(
            capability_id="governance.status",
            category="governance",
            access_level="read",
            handler="system.governance_status",
            description="Return active external-agent governance boundaries.",
        ), governance_status),
    ]
