from __future__ import annotations

from pathlib import Path

from models.architecture_decision_record import ArchitectureDecisionRecordStatus
from models.proposal import Proposal, ProposalStatus, ProposalType
from services.architecture_decision_record_service import ArchitectureDecisionRecordService
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


def _adr(tmp_path: Path) -> tuple[str, str]:
    adr = ArchitectureDecisionRecordService(tmp_path).propose_adr(
        project_id="Ageix",
        session_id="session-1",
        created_by="lex",
        title="Governed ADR routing",
        context="Context",
        decision="Decision",
        rationale="Rationale",
    )
    return adr.adr_id, adr.proposal_id


def _payload(action: str, target_id: str, target_type: str = "proposal") -> dict:
    return {
        "project_id": "Ageix",
        "target_record_id": target_id,
        "target_record_type": target_type,
        "action": action,
        "rationale": "Required rationale.",
    }


def test_valid_proposal_action_routes_to_target_capability_without_adapter_mutation(tmp_path: Path) -> None:
    _proposal(tmp_path, "PROP-HI-ROUTE")

    result = HumanInterfaceGovernedApprovalService(tmp_path).execute(_payload("approve", "PROP-HI-ROUTE"), _identity())

    assert result["success"] is True
    assert result["routed_capability_id"] == "proposal.approval.execute"
    assert result["capability_id"] == "proposal.approval.execute"
    assert result["mutation_performed_by_human_interface"] is False
    assert result["mutation_performed_by_adapter"] is False
    proposal = ProposalService(tmp_path).get_proposal("PROP-HI-ROUTE")
    assert proposal.status == ProposalStatus.APPROVED
    assert not (tmp_path / ".ageix" / "architecture" / "adrs").exists()


def test_valid_adr_action_routes_to_target_capability_without_adapter_mutation(tmp_path: Path) -> None:
    adr_id, proposal_id = _adr(tmp_path)
    ProposalService(tmp_path).update_status(proposal_id, ProposalStatus.APPROVED)
    proposal_before = ProposalService(tmp_path).get_proposal(proposal_id).model_dump()

    result = HumanInterfaceGovernedApprovalService(tmp_path).execute(_payload("approve", adr_id, "adr"), _identity())

    assert result["success"] is True
    assert result["routed_capability_id"] == "architecture.adr.approval.execute"
    assert result["capability_id"] == "architecture.adr.approval.execute"
    assert result["mutation_performed_by_human_interface"] is False
    assert result["mutation_performed_by_adapter"] is False
    adr = ArchitectureDecisionRecordService(tmp_path).get_adr(adr_id)
    assert adr["status"] == ArchitectureDecisionRecordStatus.ACCEPTED.value
    assert ProposalService(tmp_path).get_proposal(proposal_id).model_dump() == proposal_before


def test_missing_rationale_rejected_before_routing(tmp_path: Path) -> None:
    _proposal(tmp_path, "PROP-HI-RATIONALE")
    payload = _payload("approve", "PROP-HI-RATIONALE")
    payload["rationale"] = ""

    result = HumanInterfaceGovernedApprovalService(tmp_path).execute(payload, _identity())

    assert result["success"] is False
    assert result["error"] == "rationale_required"
    proposal = ProposalService(tmp_path).get_proposal("PROP-HI-RATIONALE")
    assert proposal.status == ProposalStatus.SUBMITTED
