from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition


SUPPORTED_ACTIONS = {"approve", "reject", "defer", "request_changes", "add_comment"}
TARGET_CAPABILITY_ROUTES = {
    "proposal": "proposal.approval.execute",
    "pending_proposal": "proposal.approval.execute",
    "architecture_decision": "architecture.adr.approval.execute",
    "architecture_decision_record": "architecture.adr.approval.execute",
    "pending_architecture_decision": "architecture.adr.approval.execute",
    "adr": "architecture.adr.approval.execute",
}


def register_capabilities(repo_root: Path):
    def execute_approval(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            clean = _validated(arguments)
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        target_capability_id = TARGET_CAPABILITY_ROUTES[clean["target_record_type"]]
        return _capability_unavailable(clean, target_capability_id)

    return [
        (CapabilityDefinition(
            capability_id="human_interface.approval.execute",
            category="human_interface",
            access_level="governed_write",
            handler="human_interface.approval.execute",
            description="Route Human Interface approval actions to existing target-specific governed approval capabilities; does not implement approval semantics.",
            requires_proposal=False,
            requires_consultation=False,
            exposed_to_external_agents=True,
        ), execute_approval),
    ]


def _validated(arguments: dict[str, Any]) -> dict[str, str]:
    project_id = str(arguments.get("project_id") or "").strip()
    target_record_id = str(arguments.get("target_record_id") or "").strip()
    target_record_type = str(arguments.get("target_record_type") or "").strip().lower()
    action = str(arguments.get("action") or "").strip().lower()
    rationale = str(arguments.get("rationale") or "").strip()

    if not project_id:
        raise ValueError("project_id_required")
    if project_id != "Ageix":
        raise ValueError("project_scope_denied")
    if not target_record_id:
        raise ValueError("target_record_id_required")
    if not target_record_type:
        raise ValueError("target_record_type_required")
    if target_record_type not in TARGET_CAPABILITY_ROUTES:
        raise ValueError("invalid_target")
    if not action:
        raise ValueError("action_required")
    if action not in SUPPORTED_ACTIONS:
        raise ValueError("unsupported_action")
    if not rationale:
        raise ValueError("rationale_required")
    return {
        "project_id": project_id,
        "target_record_id": target_record_id,
        "target_record_type": target_record_type,
        "action": action,
        "rationale": rationale,
    }


def _capability_unavailable(clean: dict[str, str], target_capability_id: str) -> dict[str, Any]:
    return {
        "success": False,
        "result": {
            "project_id": clean["project_id"],
            "target_record_id": clean["target_record_id"],
            "target_record_type": clean["target_record_type"],
            "action": clean["action"],
            "routed_capability_id": target_capability_id,
            "mutation_performed_by_human_interface": False,
            "approval_semantics_implemented_by_human_interface": False,
            "required_target_capability_available": False,
        },
        "error": "capability_unavailable",
        "metadata": {
            "source": "human_interface_approval_router",
            "routed_capability_id": target_capability_id,
            "gap": "target_specific_governed_approval_capability_missing",
        },
    }
