from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from models.proposal import ProposalStatus
from services.architecture_decision_record_service import ArchitectureDecisionRecordService
from services.decision_trace_service import DecisionTraceService
from services.proposal_service import ProposalService


SUPPORTED_ACTIONS = {"approve", "reject", "defer", "request_changes", "add_comment"}
SUPPORTED_TARGET_TYPES = {
    "proposal",
    "pending_proposal",
    "architecture_decision",
    "architecture_decision_record",
    "pending_architecture_decision",
    "adr",
}
GOVERNING_ARTIFACT_IDS = [
    "EVPKG-298023C1EE14",
    "ADR-0017",
    "ADR-1CE374A025B2",
    "PRIN-0007",
    "INTENT-0008",
    "ARCHREV-2F16C935631A",
]


def register_capabilities(repo_root: Path):
    proposal_service = ProposalService(repo_root)
    adr_service = ArchitectureDecisionRecordService(repo_root)
    trace_service = DecisionTraceService(repo_root)

    def execute_approval(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            clean = _validated(arguments)
            if clean["target_record_type"] in {"proposal", "pending_proposal"}:
                result = _execute_proposal_action(clean, arguments, proposal_service, trace_service)
            else:
                result = _execute_adr_action(clean, arguments, proposal_service, adr_service, trace_service)
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        except PermissionError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": result, "metadata": {"source": "human_interface_approval_capability"}}

    return [
        (CapabilityDefinition(
            capability_id="human_interface.approval.execute",
            category="human_interface",
            access_level="governed_write",
            handler="human_interface.approval.execute",
            description="Execute Human Interface approval actions through existing Ageix governance services; adapter remains translation-only.",
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
    if target_record_type not in SUPPORTED_TARGET_TYPES:
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


def _execute_proposal_action(
    clean: dict[str, str],
    arguments: dict[str, Any],
    proposals: ProposalService,
    traces: DecisionTraceService,
) -> dict[str, Any]:
    proposal = proposals.get_proposal(clean["target_record_id"])
    if proposal.project_id != clean["project_id"]:
        raise ValueError("project_scope_denied")
    status = _proposal_status_for_action(clean["action"], proposal.status)
    metadata = _merged_metadata(proposal.metadata, clean, arguments)
    updates: dict[str, Any] = {"metadata": metadata}
    if clean["action"] == "request_changes":
        existing_conditions = list(proposal.conditions or [])
        existing_conditions.append(clean["rationale"])
        updates["conditions"] = existing_conditions
    updated = proposals.update_status(proposal.proposal_id, status, **updates)
    trace = _create_trace(clean, arguments, traces, proposal_id=proposal.proposal_id, updated_status=updated.status.value)
    return _success_payload(clean, arguments, updated.status.value, trace.trace_id, trace.decision_id, [proposal.proposal_id])


def _execute_adr_action(
    clean: dict[str, str],
    arguments: dict[str, Any],
    proposals: ProposalService,
    adrs: ArchitectureDecisionRecordService,
    traces: DecisionTraceService,
) -> dict[str, Any]:
    adr = adrs.get_adr(clean["target_record_id"])
    if adr.get("project_id") != clean["project_id"]:
        raise ValueError("project_scope_denied")
    proposal_id = str(adr.get("proposal_id") or "")
    if not proposal_id:
        raise ValueError("invalid_target")
    proposal = proposals.get_proposal(proposal_id)
    status = _proposal_status_for_action(clean["action"], proposal.status)
    metadata = _merged_metadata(proposal.metadata, clean, arguments)
    updates: dict[str, Any] = {"metadata": metadata}
    if clean["action"] == "request_changes":
        existing_conditions = list(proposal.conditions or [])
        existing_conditions.append(clean["rationale"])
        updates["conditions"] = existing_conditions
    proposals.update_status(proposal.proposal_id, status, **updates)
    trace = _create_trace(
        clean,
        arguments,
        traces,
        proposal_id=proposal.proposal_id,
        updated_status=status.value,
        evidence_package_ids=list(adr.get("evidence_package_ids") or []),
    )
    governing_ids = [proposal.proposal_id]
    updated_status = status.value
    if clean["action"] == "approve":
        accepted = adrs.accept_approved_adr(
            clean["target_record_id"],
            approved_by=_actor(arguments),
            decision_trace_id=trace.trace_id,
            evidence_package_ids=list(adr.get("evidence_package_ids") or []),
            metadata={"human_interface_action": clean["action"], "rationale": clean["rationale"]},
        )
        updated_status = str(accepted.status.value if hasattr(accepted.status, "value") else accepted.status)
        governing_ids.append(accepted.adr_id)
    else:
        governing_ids.append(clean["target_record_id"])
    return _success_payload(clean, arguments, updated_status, trace.trace_id, trace.decision_id, governing_ids)


def _proposal_status_for_action(action: str, current: Any) -> ProposalStatus:
    if action == "approve":
        return ProposalStatus.APPROVED
    if action == "reject":
        return ProposalStatus.DENIED
    if action in {"defer", "request_changes"}:
        return ProposalStatus.UNDER_REVIEW
    return ProposalStatus(str(current.value if hasattr(current, "value") else current))


def _trace_outcome_for_action(action: str) -> str:
    if action == "approve":
        return "approved"
    if action == "reject":
        return "rejected"
    if action == "defer":
        return "deferred"
    return "backlog"


def _create_trace(
    clean: dict[str, str],
    arguments: dict[str, Any],
    traces: DecisionTraceService,
    *,
    proposal_id: str | None,
    updated_status: str,
    evidence_package_ids: list[str] | None = None,
):
    return traces.create_trace(
        decision_summary=f"Human Interface {clean['action']} for {clean['target_record_type']} {clean['target_record_id']}",
        outcome=_trace_outcome_for_action(clean["action"]),
        requester_identity=_identity(arguments),
        decision_type="human_interface_governed_approval",
        proposal_id=proposal_id,
        evidence_package_ids=evidence_package_ids or [],
        reason=clean["rationale"],
        outcome_metadata={
            "action": clean["action"],
            "updated_status": updated_status,
            "adapter_translation_only": True,
            "governance_reused": True,
        },
        related_entities={clean["target_record_type"]: [clean["target_record_id"]]},
        metadata={
            "source": "human_interface_approval_capability",
            "open_webui_state_created": False,
            "adapter_mutated_repository": False,
        },
    )


def _merged_metadata(existing: dict[str, Any], clean: dict[str, str], arguments: dict[str, Any]) -> dict[str, Any]:
    comments = list(dict(existing or {}).get("human_interface_comments") or [])
    comments.append({
        "action": clean["action"],
        "rationale": clean["rationale"],
        "actor": _actor(arguments),
        "recorded_at": _now(),
    })
    return {
        **dict(existing or {}),
        "last_human_interface_action": clean["action"],
        "last_human_interface_actor": _actor(arguments),
        "last_human_interface_action_at": _now(),
        "human_interface_comments": comments,
    }


def _success_payload(
    clean: dict[str, str],
    arguments: dict[str, Any],
    updated_status: str,
    trace_id: str,
    decision_id: str,
    governing_artifact_ids: list[str],
) -> dict[str, Any]:
    return {
        "success": True,
        "project_id": clean["project_id"],
        "target_record_id": clean["target_record_id"],
        "target_record_type": clean["target_record_type"],
        "action": clean["action"],
        "updated_status": updated_status,
        "decision_trace_identifier": trace_id,
        "decision_id": decision_id,
        "audit_reference": f"capability_audit:human_interface.approval.execute:{trace_id}",
        "validation_reference": None,
        "governing_artifact_identifiers": list(dict.fromkeys([*GOVERNING_ARTIFACT_IDS, *governing_artifact_ids])),
        "timestamp": _now(),
        "acting_identity": _identity(arguments),
        "execution_flow": [
            "human_interface_adapter",
            "capability_authorization",
            "human_interface.approval.execute",
            "decision_trace_service",
            "capability_audit_service",
            "ageix_system_of_record",
        ],
    }


def _identity(arguments: dict[str, Any]) -> dict[str, Any]:
    provided = dict(arguments.get("authenticated_identity") or {})
    return {
        "authenticated": bool(provided.get("authenticated", True)),
        "agent_id": str(arguments.get("agent_id") or provided.get("agent_id") or "chair"),
        "agent_role": str(arguments.get("agent_role") or provided.get("agent_role") or "ageix.chair"),
        "client_id": str(arguments.get("client_id") or provided.get("client_id") or "human_interface"),
        "provider": str(arguments.get("provider") or provided.get("provider") or "human_interface"),
        "session_id": str(arguments.get("session_id") or provided.get("session_id") or "human-interface"),
        "project_id": str(arguments.get("project_id") or provided.get("project_id") or "Ageix"),
        "participant_id": arguments.get("participant_id") or provided.get("participant_id"),
        "authority_granted": False,
    }


def _actor(arguments: dict[str, Any]) -> str:
    return str(arguments.get("agent_id") or arguments.get("client_id") or "chair")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
