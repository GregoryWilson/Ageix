from pathlib import Path

from models.agent_profile import AgentProfile
from models.capability_request import CapabilityRequest
from models.evidence_access_proposal import EvidenceAccessProposal, EvidenceRequestItem
from services.agent_profile_service import AgentProfileService
from services.agent_session_service import AgentSessionService
from services.approval_request_service import ApprovalRequestService
from services.capability_execution_service import CapabilityExecutionService
from services.current_project_resolution_service import CurrentProjectResolutionService
from services.evidence_access_proposal_service import EvidenceAccessProposalService
from services.project_profile_service import ProjectProfileService


def _seed_project(tmp_path: Path, project_id: str = "Ageix"):
    return ProjectProfileService(tmp_path).register_project(project_id, project_id, "python", tmp_path)


def test_resolve_current_project(tmp_path: Path):
    _seed_project(tmp_path)
    AgentSessionService(tmp_path).create_session("thread-1", "lex", project_id="Ageix")

    resolved = CurrentProjectResolutionService(tmp_path).resolve_project_id("current", "thread-1")

    assert resolved == "Ageix"


def test_project_current_capability(tmp_path: Path):
    _seed_project(tmp_path)
    AgentSessionService(tmp_path).create_session("thread-1", "lex", project_id="Ageix")

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="project.current",
        session_id="thread-1",
        agent_id="lex",
        arguments={},
    ))

    assert response.success is True
    assert response.result["project_id"] == "Ageix"
    assert "root_path" not in response.result


def test_section_symbol_resolution(tmp_path: Path):
    _seed_project(tmp_path)
    (tmp_path / "foo.py").write_text("def run():\n    return True\n\ndef other():\n    return False\n", encoding="utf-8")

    decision = EvidenceAccessProposalService(tmp_path).evaluate(EvidenceAccessProposal(
        session_id="thread-1",
        agent_id="lex",
        project_id="current",
        objective="Review run behavior",
        reason="Need exact symbol implementation for review",
        requested_evidence=[EvidenceRequestItem(
            type="section",
            path="foo.py",
            symbol="run",
            reason="Need exact symbol implementation for review",
        )],
    ))

    assert decision.decision == "approved"
    assert "def run" in decision.approved_evidence[0]["content"]


def test_section_line_range_resolution(tmp_path: Path):
    _seed_project(tmp_path)
    (tmp_path / "foo.py").write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")

    decision = EvidenceAccessProposalService(tmp_path).evaluate(EvidenceAccessProposal(
        session_id="thread-1",
        agent_id="lex",
        project_id="current",
        objective="Review exact lines",
        reason="Need exact line range for review",
        requested_evidence=[EvidenceRequestItem(
            type="section",
            path="foo.py",
            start_line=2,
            end_line=3,
            reason="Need exact line range for review",
        )],
    ))

    assert decision.decision == "approved"
    assert decision.approved_evidence[0]["content"] == "line2\nline3\n"


def test_descriptive_validation_errors(tmp_path: Path):
    _seed_project(tmp_path)
    (tmp_path / "foo.py").write_text("print('x')\n", encoding="utf-8")

    decision = EvidenceAccessProposalService(tmp_path).evaluate(EvidenceAccessProposal(
        session_id="thread-1",
        agent_id="lex",
        project_id="Ageix",
        objective="Review file",
        reason="Need review",
        requested_evidence=[EvidenceRequestItem(type="file", path="foo.py", reason="why")],
    ))

    assert decision.decision == "denied"
    details = decision.denied_evidence[0]["details"]
    assert decision.denied_evidence[0]["reason"] == "evidence_request_reason_too_sparse"
    assert "specificity_score" in details
    assert details["required_minimum"] == 0.5


def test_create_approval_request(tmp_path: Path):
    request = ApprovalRequestService(tmp_path).create_request(
        proposal_id="EAP-1",
        reason="evidence_request_exceeds_reputation_budget",
        requested_by="lex",
        request_type="evidence_expansion",
    )

    assert request.status == "pending"
    assert request.request_type == "evidence_expansion"


def test_persist_approval_request(tmp_path: Path):
    created = ApprovalRequestService(tmp_path).create_request(proposal_id="EAP-1", reason="Needs approval", requested_by="lex")

    loaded = ApprovalRequestService(tmp_path).get_request(created.approval_id)

    assert loaded.approval_id == created.approval_id


def test_approval_request_status(tmp_path: Path):
    service = ApprovalRequestService(tmp_path)
    created = service.create_request(proposal_id="EAP-1", reason="Needs approval", requested_by="lex")

    updated = service.update_status(created.approval_id, "approved")

    assert updated.status == "approved"


def test_agent_list(tmp_path: Path):
    AgentProfileService(tmp_path).upsert_profile(AgentProfile(agent_id="lex", reputation_level="strategic", notes="Long-term architecture participant"))

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="agent.list",
        session_id="thread-1",
        agent_id="lex",
        arguments={},
    ))

    assert response.success is True
    assert response.result["agents"][0]["agent_id"] == "lex"
    assert response.result["agents"][0]["reputation_level"] == "strategic"


def test_agent_profile(tmp_path: Path):
    AgentProfileService(tmp_path).upsert_profile(AgentProfile(agent_id="lex", reputation_level="strategic", notes="Long-term architecture participant"))

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="agent.profile",
        session_id="thread-1",
        agent_id="lex",
        arguments={"profile_agent_id": "lex"},
    ))

    assert response.success is True
    assert response.result["agent_id"] == "lex"
    assert response.result["reputation_level"] == "strategic"
    assert "reputation_score" not in response.result


def test_create_agent_session(tmp_path: Path):
    session = AgentSessionService(tmp_path).create_session("thread-1", "lex", project_id="Ageix")

    assert session.session_id == "thread-1"
    assert session.project_id == "Ageix"


def test_update_last_activity(tmp_path: Path):
    service = AgentSessionService(tmp_path)
    service.create_session("thread-1", "lex")

    updated = service.record_capability_use("thread-1", "lex", "ageix.health")

    assert updated.last_activity is not None
    assert "ageix.health" in updated.capabilities_used


def test_session_project_resolution(tmp_path: Path):
    _seed_project(tmp_path)
    AgentSessionService(tmp_path).create_session("thread-1", "lex", project_id="Ageix")
    (tmp_path / "foo.py").write_text("print('x')\n", encoding="utf-8")

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.request",
        session_id="thread-1",
        agent_id="lex",
        arguments={
            "objective": "Review file",
            "reason": "Need exact file implementation for review",
            "requested_evidence": [{"type": "file", "path": "foo.py", "reason": "Need exact file implementation for review"}],
        },
    ))

    assert response.success is True
    assert response.metadata["project_id"] == "Ageix"


def test_current_project_does_not_bypass_governance(tmp_path: Path):
    _seed_project(tmp_path)
    AgentSessionService(tmp_path).create_session("thread-1", "lex", project_id="Ageix")

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="repository.raw_read",
        session_id="thread-1",
        agent_id="lex",
        arguments={"project_id": "current", "path": "foo.py"},
    ))

    assert response.success is False
    assert response.error == "external_agents_cannot_bypass_repository_governance"


def test_human_approval_still_required(tmp_path: Path):
    _seed_project(tmp_path)
    for index in range(3):
        (tmp_path / f"file_{index}.py").write_text("print('x')\n", encoding="utf-8")

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.request",
        session_id="thread-1",
        agent_id="new_agent",
        arguments={
            "project_id": "current",
            "objective": "Review three files",
            "reason": "Need broad implementation comparison",
            "requested_evidence": [
                {"type": "file", "path": f"file_{index}.py", "reason": "Need exact file implementation comparison"}
                for index in range(3)
            ],
        },
    ))

    assert response.success is False
    assert response.error == "human_approval_required"
    assert response.metadata["approval_id"].startswith("APR-")
