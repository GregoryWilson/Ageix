import json
import subprocess
import sys
from pathlib import Path

from models.capability_request import CapabilityRequest
from models.proposal import Proposal, ProposalStatus, ProposalType
from services.agent_session_service import AgentSessionService
from services.capability_execution_service import CapabilityExecutionService
from services.consultation_evidence_review_service import ConsultationEvidenceReviewService
from services.project_profile_service import ProjectProfileService
from services.proposal_evaluation_service import ProposalEvaluationService
from services.proposal_service import ProposalService


def _seed_project(tmp_path: Path, project_id: str = "Ageix"):
    ProjectProfileService(tmp_path).register_project(project_id, project_id, "python", tmp_path)
    AgentSessionService(tmp_path).create_session("thread-1", "lex", project_id=project_id)


def _submit_external_consultation(tmp_path: Path, proposal_id: str):
    return CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="consultation.submit",
        session_id="thread-1",
        agent_id="lex",
        arguments={
            "proposal_id": proposal_id,
            "consultation_type": "architecture_review",
            "summary": "External review supports the proposal.",
            "findings": ["Governance boundary preserved."],
            "confidence": 0.82,
            "evidence_sufficient": True,
        },
    ))


def test_evidence_access_proposal_uses_disambiguated_capability_name(tmp_path: Path):
    _seed_project(tmp_path)
    (tmp_path / "foo.py").write_text("def run():\n    return True\n", encoding="utf-8")

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.proposal.submit",
        session_id="thread-1",
        agent_id="lex",
        arguments={
            "project_id": "Ageix",
            "objective": "Review run function",
            "reason": "Need exact function implementation",
            "requested_evidence": [{
                "type": "symbol",
                "path": "foo.py",
                "symbol": "run",
                "reason": "Need exact function implementation",
            }],
        },
    ))

    assert response.success is True
    assert response.metadata["capability_id"] == "evidence.proposal.submit"
    assert response.metadata["proposal_type"] == "evidence_access"


def test_general_proposal_submit_no_longer_handles_evidence_access(tmp_path: Path):
    _seed_project(tmp_path)

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="proposal.submit",
        session_id="thread-1",
        agent_id="lex",
        arguments={"project_id": "Ageix", "objective": "Evidence", "proposal_type": "evidence_access"},
    ))

    assert response.success is False
    assert "evidence_access" in response.error


def test_external_consultation_links_by_id_and_details_fetches_payload(tmp_path: Path):
    _seed_project(tmp_path)
    proposal = ProposalService(tmp_path).create_proposal(Proposal(
        project_id="Ageix",
        session_id="thread-1",
        agent_id="lex",
        objective="Review architecture direction",
        proposal_type=ProposalType.ARCHITECTURE,
        required_consultations=["architecture_review"],
    ))

    submitted = _submit_external_consultation(tmp_path, proposal.proposal_id)

    assert submitted.success is True
    consultation_id = submitted.result["consultation_id"]
    updated = ProposalService(tmp_path).get_proposal(proposal.proposal_id)
    assert updated.status == ProposalStatus.CONSULTATION_SUBMITTED
    assert updated.linked_consultations == [consultation_id]

    details = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="consultation.details",
        session_id="thread-1",
        agent_id="lex",
        arguments={"consultation_id": consultation_id},
    ))

    assert details.success is True
    assert details.result["consultation_id"] == consultation_id
    assert details.result["response"]["metadata"]["source"] == "external_agent_submitted_consultation"


def test_chair_accepts_consultation_and_satisfies_required_type(tmp_path: Path):
    _seed_project(tmp_path)
    proposal = ProposalService(tmp_path).create_proposal(Proposal(
        project_id="Ageix",
        session_id="thread-1",
        agent_id="lex",
        objective="Review architecture direction",
        proposal_type=ProposalType.ARCHITECTURE,
        required_consultations=["architecture_review"],
    ))
    submitted = _submit_external_consultation(tmp_path, proposal.proposal_id)
    consultation_id = submitted.result["consultation_id"]

    ConsultationEvidenceReviewService(tmp_path).accept(consultation_id, chair_id="chair", reason="Sufficient architecture review.")
    result = ProposalEvaluationService(tmp_path).evaluate(proposal.proposal_id)
    updated = ProposalService(tmp_path).get_proposal(proposal.proposal_id)

    assert consultation_id in updated.accepted_consultations
    assert "architecture_review" in updated.required_consultations
    assert "architecture_review" in updated.satisfied_consultations
    assert result.disposition == "approved"


def test_lower_service_can_recommend_rejection_but_not_reject(tmp_path: Path):
    _seed_project(tmp_path)
    proposal = ProposalService(tmp_path).create_proposal(Proposal(
        project_id="Ageix",
        session_id="thread-1",
        agent_id="lex",
        objective="Review architecture direction",
        proposal_type=ProposalType.ARCHITECTURE,
        required_consultations=["architecture_review"],
    ))
    submitted = _submit_external_consultation(tmp_path, proposal.proposal_id)
    consultation_id = submitted.result["consultation_id"]

    service = ConsultationEvidenceReviewService(tmp_path)
    service.recommend_rejection(consultation_id, reviewer_id="quality_gate", reason="Missing supporting evidence.")
    session = service.details(consultation_id)
    updated = ProposalService(tmp_path).get_proposal(proposal.proposal_id)

    assert session["status"] == "submitted"
    assert session["review_recommendations"][0]["chair_authoritative"] is False
    assert consultation_id not in updated.rejected_consultations


def test_chair_rejects_consultation_authoritatively(tmp_path: Path):
    _seed_project(tmp_path)
    proposal = ProposalService(tmp_path).create_proposal(Proposal(
        project_id="Ageix",
        session_id="thread-1",
        agent_id="lex",
        objective="Review architecture direction",
        proposal_type=ProposalType.ARCHITECTURE,
        required_consultations=["architecture_review"],
    ))
    submitted = _submit_external_consultation(tmp_path, proposal.proposal_id)
    consultation_id = submitted.result["consultation_id"]

    ConsultationEvidenceReviewService(tmp_path).reject(consultation_id, chair_id="chair", reason="Insufficient evidence.")
    updated = ProposalService(tmp_path).get_proposal(proposal.proposal_id)

    assert consultation_id in updated.rejected_consultations
    assert consultation_id not in updated.accepted_consultations
    assert "architecture_review" not in updated.satisfied_consultations


def test_chair_proposal_mode_submits_without_discovery(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "chair.py",
            "--mode",
            "proposal",
            "--objective",
            "Propose explicit proposal routing smoke.",
            "--project-id",
            "Ageix_Test",
            "--proposal-type",
            "architecture",
            "--session-id",
            "smoke-13-1",
            "--agent-id",
            "lex",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["mode"] == "proposal"
    assert payload["chair_action"] == "proposal_submitted"
    assert payload["capability_response"]["result"]["proposal"]["status"] == "awaiting_consultation"
