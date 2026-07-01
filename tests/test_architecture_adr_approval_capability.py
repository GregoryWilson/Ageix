from __future__ import annotations

from pathlib import Path

from models.architecture_decision_record import ArchitectureDecisionRecordStatus
from models.capability_request import CapabilityRequest
from models.proposal import ProposalStatus
from services.architecture_decision_record_service import ArchitectureDecisionRecordService
from services.capability_execution_service import CapabilityExecutionService
from services.proposal_service import ProposalService


def _adr(tmp_path: Path) -> tuple[str, str]:
    adr = ArchitectureDecisionRecordService(tmp_path).propose_adr(
        project_id="Ageix",
        session_id="session-1",
        created_by="lex",
        title="Governed ADR approval",
        context="Context",
        decision="Decision",
        rationale="Rationale",
    )
    return adr.adr_id, adr.proposal_id


def _execute(tmp_path: Path, *, adr_id: str, action: str, agent_role: str = "ageix.chair", project_id: str = "Ageix", rationale: str = "Human rationale.") -> dict:
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="architecture.adr.approval.execute",
        session_id="adr-approval-test",
        agent_id="chair",
        arguments={
            "project_id": project_id,
            "target_record_id": adr_id,
            "target_record_type": "adr",
            "action": action,
            "rationale": rationale,
            "client_id": "human_interface",
            "provider": "human_interface",
            "agent_role": agent_role,
            "authenticated_identity": {"authenticated": True},
        },
    ))
    if response.success:
        return response.result
    return {**dict(response.result or {}), "success": False, "error": response.error}


def test_adr_approval_rejects_non_chair_role(tmp_path: Path) -> None:
    adr_id, _proposal_id = _adr(tmp_path)

    result = _execute(tmp_path, adr_id=adr_id, action="approve", agent_role="lex")

    assert result["success"] is False
    assert result["error"] == "authorization_failure"
    assert ArchitectureDecisionRecordService(tmp_path).get_adr(adr_id)["status"] == ArchitectureDecisionRecordStatus.PROPOSED.value


def test_adr_approve_mutates_only_adr_lifecycle_state(tmp_path: Path) -> None:
    adr_id, proposal_id = _adr(tmp_path)
    ProposalService(tmp_path).update_status(proposal_id, ProposalStatus.APPROVED)
    proposal_before = ProposalService(tmp_path).get_proposal(proposal_id).model_dump()

    result = _execute(tmp_path, adr_id=adr_id, action="approve")

    assert result["success"] is True
    assert result["capability_id"] == "architecture.adr.approval.execute"
    assert result["status_before"] == ArchitectureDecisionRecordStatus.PROPOSED.value
    assert result["status_after"] == ArchitectureDecisionRecordStatus.ACCEPTED.value
    assert result["mutation_performed_by_human_interface"] is False
    assert result["mutation_performed_by_target_capability"] is True
    adr = ArchitectureDecisionRecordService(tmp_path).get_adr(adr_id)
    assert adr["status"] == ArchitectureDecisionRecordStatus.ACCEPTED.value
    proposal_after = ProposalService(tmp_path).get_proposal(proposal_id).model_dump()
    assert proposal_after == proposal_before


def test_adr_reject_mutates_only_adr_lifecycle_state(tmp_path: Path) -> None:
    adr_id, proposal_id = _adr(tmp_path)
    proposal_before = ProposalService(tmp_path).get_proposal(proposal_id).model_dump()

    result = _execute(tmp_path, adr_id=adr_id, action="reject")

    assert result["success"] is True
    assert result["status_before"] == ArchitectureDecisionRecordStatus.PROPOSED.value
    assert result["status_after"] == ArchitectureDecisionRecordStatus.REJECTED.value
    adr = ArchitectureDecisionRecordService(tmp_path).get_adr(adr_id)
    assert adr["status"] == ArchitectureDecisionRecordStatus.REJECTED.value
    proposal_after = ProposalService(tmp_path).get_proposal(proposal_id).model_dump()
    assert proposal_after == proposal_before


def test_adr_add_comment_does_not_change_lifecycle_state(tmp_path: Path) -> None:
    adr_id, _proposal_id = _adr(tmp_path)

    result = _execute(tmp_path, adr_id=adr_id, action="add_comment")

    assert result["success"] is True
    assert result["status_before"] == ArchitectureDecisionRecordStatus.PROPOSED.value
    assert result["status_after"] == ArchitectureDecisionRecordStatus.PROPOSED.value
    adr = ArchitectureDecisionRecordService(tmp_path).get_adr(adr_id)
    assert adr["status"] == ArchitectureDecisionRecordStatus.PROPOSED.value
    assert adr["metadata"]["governance_comments"][0]["action"] == "add_comment"


def test_adr_invalid_project_denied_before_mutation(tmp_path: Path) -> None:
    adr_id, _proposal_id = _adr(tmp_path)

    result = _execute(tmp_path, adr_id=adr_id, action="approve", project_id="Other")

    assert result["success"] is False
    assert result["error"] == "project_scope_denied"
    assert ArchitectureDecisionRecordService(tmp_path).get_adr(adr_id)["status"] == ArchitectureDecisionRecordStatus.PROPOSED.value


def test_adr_missing_rationale_denied_before_mutation(tmp_path: Path) -> None:
    adr_id, _proposal_id = _adr(tmp_path)

    result = _execute(tmp_path, adr_id=adr_id, action="approve", rationale="")

    assert result["success"] is False
    assert result["error"] == "rationale_required"
    assert ArchitectureDecisionRecordService(tmp_path).get_adr(adr_id)["status"] == ArchitectureDecisionRecordStatus.PROPOSED.value


def test_adr_unsupported_action_denied_before_mutation(tmp_path: Path) -> None:
    adr_id, _proposal_id = _adr(tmp_path)

    result = _execute(tmp_path, adr_id=adr_id, action="escalate")

    assert result["success"] is False
    assert result["error"] == "unsupported_action"
    assert ArchitectureDecisionRecordService(tmp_path).get_adr(adr_id)["status"] == ArchitectureDecisionRecordStatus.PROPOSED.value


def test_adr_defer_reports_unsupported_for_current_target_lifecycle(tmp_path: Path) -> None:
    adr_id, _proposal_id = _adr(tmp_path)

    result = _execute(tmp_path, adr_id=adr_id, action="defer")

    assert result["success"] is False
    assert result["error"] == "unsupported_action_for_target"
    assert ArchitectureDecisionRecordService(tmp_path).get_adr(adr_id)["status"] == ArchitectureDecisionRecordStatus.PROPOSED.value
