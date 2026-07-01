from __future__ import annotations

from pathlib import Path

from models.capability_request import CapabilityRequest
from models.proposal import Proposal, ProposalStatus, ProposalType
from services.capability_execution_service import CapabilityExecutionService
from services.proposal_service import ProposalService


def _proposal(tmp_path: Path, proposal_id: str, status: ProposalStatus = ProposalStatus.SUBMITTED) -> None:
    ProposalService(tmp_path).create_proposal(Proposal(
        proposal_id=proposal_id,
        project_id="Ageix",
        session_id="session-1",
        agent_id="lex",
        objective="Review governed proposal approval.",
        proposal_type=ProposalType.IMPLEMENTATION,
        status=status,
        metadata={},
    ))


def _execute(tmp_path: Path, *, proposal_id: str, action: str, agent_role: str = "ageix.chair", project_id: str = "Ageix", rationale: str = "Human rationale.") -> dict:
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="proposal.approval.execute",
        session_id="proposal-approval-test",
        agent_id="chair",
        arguments={
            "project_id": project_id,
            "target_record_id": proposal_id,
            "target_record_type": "proposal",
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


def test_proposal_approval_rejects_non_chair_role(tmp_path: Path) -> None:
    _proposal(tmp_path, "PROP-NONCHAIR")

    result = _execute(tmp_path, proposal_id="PROP-NONCHAIR", action="approve", agent_role="lex")

    assert result["success"] is False
    assert result["error"] == "authorization_failure"
    assert ProposalService(tmp_path).get_proposal("PROP-NONCHAIR").status == ProposalStatus.SUBMITTED


def test_proposal_approve_mutates_only_proposal_lifecycle_state(tmp_path: Path) -> None:
    _proposal(tmp_path, "PROP-APPROVE")

    result = _execute(tmp_path, proposal_id="PROP-APPROVE", action="approve")

    assert result["success"] is True
    assert result["capability_id"] == "proposal.approval.execute"
    assert result["status_before"] == ProposalStatus.SUBMITTED.value
    assert result["status_after"] == ProposalStatus.APPROVED.value
    assert result["mutation_performed_by_human_interface"] is False
    assert result["mutation_performed_by_target_capability"] is True
    proposal = ProposalService(tmp_path).get_proposal("PROP-APPROVE")
    assert proposal.status == ProposalStatus.APPROVED
    assert proposal.metadata["last_governance_action"]["action"] == "approve"
    assert not (tmp_path / ".ageix" / "architecture" / "adrs").exists()


def test_proposal_reject_mutates_only_proposal_lifecycle_state(tmp_path: Path) -> None:
    _proposal(tmp_path, "PROP-REJECT")

    result = _execute(tmp_path, proposal_id="PROP-REJECT", action="reject")

    assert result["success"] is True
    assert result["status_before"] == ProposalStatus.SUBMITTED.value
    assert result["status_after"] == ProposalStatus.DENIED.value
    proposal = ProposalService(tmp_path).get_proposal("PROP-REJECT")
    assert proposal.status == ProposalStatus.DENIED
    assert proposal.metadata["last_governance_action"]["action"] == "reject"
    assert not (tmp_path / ".ageix" / "architecture" / "adrs").exists()


def test_proposal_add_comment_does_not_change_lifecycle_state(tmp_path: Path) -> None:
    _proposal(tmp_path, "PROP-COMMENT")

    result = _execute(tmp_path, proposal_id="PROP-COMMENT", action="add_comment")

    assert result["success"] is True
    assert result["status_before"] == ProposalStatus.SUBMITTED.value
    assert result["status_after"] == ProposalStatus.SUBMITTED.value
    proposal = ProposalService(tmp_path).get_proposal("PROP-COMMENT")
    assert proposal.status == ProposalStatus.SUBMITTED
    assert proposal.metadata["governance_comments"][0]["action"] == "add_comment"


def test_proposal_invalid_project_denied_before_mutation(tmp_path: Path) -> None:
    _proposal(tmp_path, "PROP-PROJECT")

    result = _execute(tmp_path, proposal_id="PROP-PROJECT", action="approve", project_id="Other")

    assert result["success"] is False
    assert result["error"] == "project_scope_denied"
    assert ProposalService(tmp_path).get_proposal("PROP-PROJECT").status == ProposalStatus.SUBMITTED


def test_proposal_missing_rationale_denied_before_mutation(tmp_path: Path) -> None:
    _proposal(tmp_path, "PROP-RATIONALE")

    result = _execute(tmp_path, proposal_id="PROP-RATIONALE", action="approve", rationale="")

    assert result["success"] is False
    assert result["error"] == "rationale_required"
    assert ProposalService(tmp_path).get_proposal("PROP-RATIONALE").status == ProposalStatus.SUBMITTED


def test_proposal_unsupported_action_denied_before_mutation(tmp_path: Path) -> None:
    _proposal(tmp_path, "PROP-UNSUPPORTED")

    result = _execute(tmp_path, proposal_id="PROP-UNSUPPORTED", action="escalate")

    assert result["success"] is False
    assert result["error"] == "unsupported_action"
    assert ProposalService(tmp_path).get_proposal("PROP-UNSUPPORTED").status == ProposalStatus.SUBMITTED


def test_proposal_defer_reports_unsupported_for_current_target_lifecycle(tmp_path: Path) -> None:
    _proposal(tmp_path, "PROP-DEFER")

    result = _execute(tmp_path, proposal_id="PROP-DEFER", action="defer")

    assert result["success"] is False
    assert result["error"] == "unsupported_action_for_target"
    assert ProposalService(tmp_path).get_proposal("PROP-DEFER").status == ProposalStatus.SUBMITTED
