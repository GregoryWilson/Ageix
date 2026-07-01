from __future__ import annotations

from pathlib import Path

from models.proposal import Proposal, ProposalStatus, ProposalType
from services.human_interface_governed_approval_service import HumanInterfaceGovernedApprovalService
from services.proposal_service import ProposalService


def _identity() -> dict:
    return {
        "authenticated": True,
        "session_id": "human-interface-test",
        "agent_id": "chair",
        "client_id": "human_interface",
        "provider": "human_interface",
        "agent_role": "ageix.chair",
        "project_id": "Ageix",
    }


def _proposal(tmp_path: Path, proposal_id: str) -> None:
    ProposalService(tmp_path).create_proposal(Proposal(
        proposal_id=proposal_id,
        project_id="Ageix",
        session_id="session-1",
        agent_id="lex",
        objective="Review governed approval routing.",
        proposal_type=ProposalType.IMPLEMENTATION,
        status=ProposalStatus.SUBMITTED,
        metadata={},
    ))


def _payload(action: str, proposal_id: str) -> dict:
    return {
        "project_id": "Ageix",
        "target_record_id": proposal_id,
        "target_record_type": "proposal",
        "action": action,
        "rationale": "Required rationale.",
    }


def test_valid_action_routes_to_missing_target_capability_without_target_mutation(tmp_path: Path) -> None:
    _proposal(tmp_path, "PROP-HI-ROUTE")

    result = HumanInterfaceGovernedApprovalService(tmp_path).execute(_payload("approve", "PROP-HI-ROUTE"), _identity())

    assert result["success"] is False
    assert result["error"] == "capability_unavailable"
    proposal = ProposalService(tmp_path).get_proposal("PROP-HI-ROUTE")
    assert proposal.status == ProposalStatus.SUBMITTED
    assert proposal.metadata == {}
    assert not (tmp_path / ".ageix" / "decision_traces").exists()


def test_missing_rationale_rejected_before_routing(tmp_path: Path) -> None:
    _proposal(tmp_path, "PROP-HI-RATIONALE")
    payload = _payload("approve", "PROP-HI-RATIONALE")
    payload["rationale"] = ""

    result = HumanInterfaceGovernedApprovalService(tmp_path).execute(payload, _identity())

    assert result["success"] is False
    assert result["error"] == "rationale_required"
    proposal = ProposalService(tmp_path).get_proposal("PROP-HI-RATIONALE")
    assert proposal.status == ProposalStatus.SUBMITTED
