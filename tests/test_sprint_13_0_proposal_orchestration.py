from pathlib import Path

from models.capability_request import CapabilityRequest
from models.proposal import Proposal, ProposalStatus, ProposalType
from services.agent_session_service import AgentSessionService
from services.capability_execution_service import CapabilityExecutionService
from services.project_profile_service import ProjectProfileService
from services.proposal_evaluation_service import ProposalEvaluationService
from services.proposal_service import ProposalService


def _seed_project(tmp_path: Path, project_id: str = "Ageix"):
    ProjectProfileService(tmp_path).register_project(project_id, project_id, "python", tmp_path)
    AgentSessionService(tmp_path).create_session("thread-1", "lex", project_id=project_id)


def test_create_proposal(tmp_path: Path):
    _seed_project(tmp_path)
    proposal = ProposalService(tmp_path).create_proposal(Proposal(
        project_id="current",
        session_id="thread-1",
        agent_id="lex",
        objective="Review architecture proposal",
        proposal_type=ProposalType.ARCHITECTURE,
    ))

    assert proposal.proposal_id.startswith("PROP-")
    assert proposal.proposal_version == 1
    assert proposal.project_id == "Ageix"
    assert proposal.status == ProposalStatus.SUBMITTED


def test_update_proposal_status(tmp_path: Path):
    _seed_project(tmp_path)
    service = ProposalService(tmp_path)
    proposal = service.create_proposal(Proposal(project_id="Ageix", session_id="thread-1", agent_id="lex", objective="Review"))

    updated = service.update_status(proposal.proposal_id, ProposalStatus.AWAITING_EVIDENCE)

    assert updated.status == ProposalStatus.AWAITING_EVIDENCE


def test_list_proposals(tmp_path: Path):
    _seed_project(tmp_path)
    service = ProposalService(tmp_path)
    service.create_proposal(Proposal(project_id="Ageix", session_id="thread-1", agent_id="lex", objective="One"))
    service.create_proposal(Proposal(project_id="Ageix", session_id="thread-1", agent_id="lex", objective="Two"))

    proposals = service.list_proposals(project_id="Ageix")

    assert len(proposals) == 2


def test_submit_proposal(tmp_path: Path):
    _seed_project(tmp_path)
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="proposal.submit",
        session_id="thread-1",
        agent_id="lex",
        arguments={"project_id": "current", "objective": "Investigate target behavior", "proposal_type": "investigation"},
    ))

    assert response.success is True
    assert response.result["proposal"]["project_id"] == "Ageix"
    assert response.result["proposal"]["proposal_version"] == 1
    assert response.result["evaluation"]["metadata"]["chair_authoritative"] is True


def test_proposal_status(tmp_path: Path):
    _seed_project(tmp_path)
    created = ProposalService(tmp_path).create_proposal(Proposal(project_id="Ageix", session_id="thread-1", agent_id="lex", objective="Review"))

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="proposal.status",
        session_id="thread-1",
        agent_id="lex",
        arguments={"proposal_id": created.proposal_id},
    ))

    assert response.success is True
    assert response.result["status"] == "submitted"


def test_proposal_details(tmp_path: Path):
    _seed_project(tmp_path)
    created = ProposalService(tmp_path).create_proposal(Proposal(project_id="Ageix", session_id="thread-1", agent_id="lex", objective="Review", parent_proposal_id="PROP-OLD", proposal_version=2))

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="proposal.details",
        session_id="thread-1",
        agent_id="lex",
        arguments={"proposal_id": created.proposal_id},
    ))

    assert response.success is True
    assert response.result["parent_proposal_id"] == "PROP-OLD"
    assert response.result["proposal_version"] == 2


def test_proposal_requires_evidence(tmp_path: Path):
    _seed_project(tmp_path)
    proposal = ProposalService(tmp_path).create_proposal(Proposal(
        project_id="Ageix",
        session_id="thread-1",
        agent_id="lex",
        objective="Implement something",
        proposal_type=ProposalType.IMPLEMENTATION,
    ))

    result = ProposalEvaluationService(tmp_path).evaluate(proposal.proposal_id)

    assert result.disposition == "consultation_required" or result.disposition == "needs_more_evidence"
    assert "proposal_requires_supporting_evidence" in result.missing_evidence


def test_proposal_requires_consultation(tmp_path: Path):
    _seed_project(tmp_path)
    proposal = ProposalService(tmp_path).create_proposal(Proposal(
        project_id="Ageix",
        session_id="thread-1",
        agent_id="lex",
        objective="Review architecture direction",
        proposal_type=ProposalType.ARCHITECTURE,
    ))

    result = ProposalEvaluationService(tmp_path).evaluate(proposal.proposal_id)

    assert result.disposition == "consultation_required"
    assert result.required_consultations == ["architecture_review"]


def test_external_consultation_submit(tmp_path: Path):
    _seed_project(tmp_path)
    proposal = ProposalService(tmp_path).create_proposal(Proposal(
        project_id="Ageix",
        session_id="thread-1",
        agent_id="lex",
        objective="Review architecture direction",
        proposal_type=ProposalType.ARCHITECTURE,
        required_consultations=["architecture_review"],
    ))

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="consultation.submit",
        session_id="thread-1",
        agent_id="lex",
        arguments={
            "proposal_id": proposal.proposal_id,
            "consultation_type": "architecture_review",
            "summary": "Greg and Lex reviewed the architecture and found the governance boundary sound.",
            "findings": ["External agents submit evidence only."],
            "recommendations": ["Chair remains authoritative."],
            "confidence": 0.8,
            "disposition": "proceed_with_recommendations",
            "evidence_sufficient": True,
        },
    ))

    assert response.success is True
    updated = ProposalService(tmp_path).get_proposal(proposal.proposal_id)
    assert updated.status == ProposalStatus.CONSULTATION_SUBMITTED
    assert response.result["consultation_id"] in updated.linked_consultations


def test_proposal_approval_path(tmp_path: Path):
    _seed_project(tmp_path)
    proposal = ProposalService(tmp_path).create_proposal(Proposal(
        project_id="Ageix",
        session_id="thread-1",
        agent_id="lex",
        objective="Investigate a low-risk behavior",
        proposal_type=ProposalType.INVESTIGATION,
        linked_evidence=["EVID-1"],
    ))

    result = ProposalEvaluationService(tmp_path).evaluate(proposal.proposal_id)

    assert result.disposition == "approved"


def test_proposal_denial_path(tmp_path: Path):
    _seed_project(tmp_path)
    proposal = ProposalService(tmp_path).create_proposal(Proposal(
        project_id="Ageix",
        session_id="thread-1",
        agent_id="lex",
        objective="Deny unsafe proposal",
        proposal_type=ProposalType.INVESTIGATION,
        linked_evidence=["EVID-1"],
    ))

    result = ProposalEvaluationService(tmp_path).evaluate(proposal.proposal_id)

    assert result.disposition == "denied"


def test_external_agent_cannot_approve(tmp_path: Path):
    _seed_project(tmp_path)
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="proposal.approve",
        session_id="thread-1",
        agent_id="lex",
        arguments={},
    ))

    assert response.success is False
    assert response.error == "unknown_capability"


def test_external_agent_cannot_modify_repo(tmp_path: Path):
    _seed_project(tmp_path)
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="repository.raw_write",
        session_id="thread-1",
        agent_id="lex",
        arguments={},
    ))

    assert response.success is False
    assert response.error == "external_agents_cannot_modify_repository"


def test_external_agent_cannot_execute_workers(tmp_path: Path):
    _seed_project(tmp_path)
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="worker.direct_execute",
        session_id="thread-1",
        agent_id="lex",
        arguments={},
    ))

    assert response.success is False
    assert response.error == "external_agents_cannot_directly_execute_workers"
