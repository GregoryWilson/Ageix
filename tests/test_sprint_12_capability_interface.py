import json
from pathlib import Path

from models.agent_profile import AgentProfile
from models.capability_definition import CapabilityDefinition
from models.capability_request import CapabilityRequest
from models.capability_response import CapabilityResponse
from models.evidence_access_proposal import EvidenceAccessProposal, EvidenceRequestItem
from services.agent_authorization_service import AgentAuthorizationService
from services.agent_profile_service import AgentProfileService
from services.capability_audit_service import CapabilityAuditService
from services.capability_execution_service import CapabilityExecutionService
from services.capability_registry_service import CapabilityRegistryService
from services.evidence_access_proposal_service import EvidenceAccessProposalService
from services.project_profile_service import ProjectProfileService


def _seed_project(tmp_path: Path, project_id: str = "Ageix"):
    ProjectProfileService(tmp_path).register_project(project_id, project_id, "python", tmp_path)


def test_register_capability(tmp_path: Path):
    registry = CapabilityRegistryService(tmp_path)
    definition = CapabilityDefinition(
        capability_id="test.echo",
        category="test",
        access_level="read",
        handler="test.echo",
    )

    registry.register(definition, lambda args: {"success": True, "result": args})

    assert registry.exists("test.echo")


def test_lookup_capability(tmp_path: Path):
    registry = CapabilityRegistryService(tmp_path)

    capability = registry.lookup("ageix.health")

    assert capability is not None
    assert capability.capability_id == "ageix.health"


def test_capability_request():
    request = CapabilityRequest(capability_id="project.list", session_id="thread-1", agent_id="lex", arguments={})

    assert request.capability_id == "project.list"
    assert request.session_id == "thread-1"


def test_capability_response():
    response = CapabilityResponse(success=True, result={"status": "ok"}, metadata={"source": "ageix"})

    assert response.success is True
    assert response.result["status"] == "ok"


def test_authorize_read_capability(tmp_path: Path):
    registry = CapabilityRegistryService(tmp_path)
    capability = registry.lookup("project.list")

    decision = AgentAuthorizationService(tmp_path).authorize("lex", capability, "project.list")

    assert decision.allowed is True


def test_deny_unauthorized_capability(tmp_path: Path):
    decision = AgentAuthorizationService(tmp_path).authorize("lex", None, "repository.raw_read")

    assert decision.allowed is False
    assert decision.reason == "external_agents_cannot_bypass_repository_governance"


def test_execute_capability(tmp_path: Path):
    request = CapabilityRequest(capability_id="ageix.health", session_id="thread-1", agent_id="lex", arguments={})

    response = CapabilityExecutionService(tmp_path).execute(request)

    assert response.success is True
    assert response.result["status"] == "ok"


def test_execute_unknown_capability(tmp_path: Path):
    request = CapabilityRequest(capability_id="does.not.exist", session_id="thread-1", agent_id="lex", arguments={})

    response = CapabilityExecutionService(tmp_path).execute(request)

    assert response.success is False
    assert response.error == "unknown_capability"


def test_capability_audit_recorded(tmp_path: Path):
    request = CapabilityRequest(capability_id="ageix.health", session_id="thread-1", agent_id="lex", arguments={})

    CapabilityExecutionService(tmp_path).execute(request)

    records = CapabilityAuditService(tmp_path).list_records()
    assert records[-1]["capability_id"] == "ageix.health"
    assert records[-1]["success"] is True


def test_project_list_capability(tmp_path: Path):
    _seed_project(tmp_path)
    request = CapabilityRequest(capability_id="project.list", session_id="thread-1", agent_id="lex", arguments={})

    response = CapabilityExecutionService(tmp_path).execute(request)

    assert response.success is True
    assert response.result["projects"][0]["project_id"] == "Ageix"
    assert "root_path" not in response.result["projects"][0]


def test_consultation_list_capability(tmp_path: Path):
    root = tmp_path / ".ageix" / "manifests" / "consultations" / "CONS-1"
    root.mkdir(parents=True)
    (root / "session.json").write_text(json.dumps({
        "consultation_id": "CONS-1",
        "status": "approved",
        "created_at": "now",
        "proposal": {"consultation_type": "architecture_review"},
        "evidence_requests": [],
        "consultation_responses": [],
    }), encoding="utf-8")

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="consultation.list",
        session_id="thread-1",
        agent_id="lex",
        arguments={},
    ))

    assert response.success is True
    assert response.result["consultations"][0]["consultation_id"] == "CONS-1"


def test_health_capability(tmp_path: Path):
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="ageix.health",
        session_id="thread-1",
        agent_id="lex",
        arguments={},
    ))

    assert response.result["capability_interface"] == "available"


def test_external_agent_cannot_access_repository(tmp_path: Path):
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="repository.raw_read",
        session_id="thread-1",
        agent_id="lex",
        arguments={"path": "services/foo.py"},
    ))

    assert response.success is False
    assert response.error == "external_agents_cannot_bypass_repository_governance"


def test_external_agent_cannot_execute_worker(tmp_path: Path):
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="worker.direct_execute",
        session_id="thread-1",
        agent_id="lex",
        arguments={"worker": "devworker"},
    ))

    assert response.success is False
    assert response.error == "external_agents_cannot_directly_execute_workers"


def test_external_agent_cannot_promote(tmp_path: Path):
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="promotion.direct_execute",
        session_id="thread-1",
        agent_id="lex",
        arguments={},
    ))

    assert response.success is False
    assert response.error == "external_agents_cannot_directly_promote_changes"


def test_evidence_access_proposal_fetches_file(tmp_path: Path):
    _seed_project(tmp_path)
    source = tmp_path / "services"
    source.mkdir()
    (source / "foo.py").write_text("class Foo:\n    pass\n", encoding="utf-8")

    proposal = EvidenceAccessProposal(
        session_id="thread-1",
        agent_id="lex",
        project_id="Ageix",
        objective="Review Foo service",
        reason="Need implementation details for review",
        requested_evidence=[EvidenceRequestItem(type="file", path="services/foo.py", reason="Need exact class implementation")],
    )

    decision = EvidenceAccessProposalService(tmp_path).evaluate(proposal)

    assert decision.decision == "approved"
    assert decision.approved_evidence[0]["content"] == "class Foo:\n    pass\n"


def test_evidence_request_capability_requires_proposal_and_audit(tmp_path: Path):
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
    assert response.metadata["requires_proposal"] is True
    assert "def run" in response.result["approved_evidence"][0]["content"]


def test_large_evidence_request_requires_human_approval_based_on_reputation_budget(tmp_path: Path):
    _seed_project(tmp_path)
    for index in range(3):
        (tmp_path / f"file_{index}.py").write_text("print('x')\n", encoding="utf-8")

    request = CapabilityRequest(
        capability_id="evidence.request",
        session_id="thread-1",
        agent_id="new_agent",
        arguments={
            "project_id": "Ageix",
            "objective": "Review three files",
            "reason": "Need broad implementation comparison",
            "requested_evidence": [
                {"type": "file", "path": f"file_{index}.py", "reason": "Need exact implementation comparison"}
                for index in range(3)
            ],
        },
    )

    response = CapabilityExecutionService(tmp_path).execute(request)

    assert response.success is False
    assert response.error == "human_approval_required"


def test_human_override_allows_budget_exceeding_evidence_request(tmp_path: Path):
    _seed_project(tmp_path)
    for index in range(3):
        (tmp_path / f"file_{index}.py").write_text("print('x')\n", encoding="utf-8")

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.request",
        session_id="thread-1",
        agent_id="new_agent",
        arguments={
            "project_id": "Ageix",
            "objective": "Review three files",
            "reason": "Need broad implementation comparison",
            "human_approval": {"approved": True, "approved_by": "greg"},
            "requested_evidence": [
                {"type": "file", "path": f"file_{index}.py", "reason": "Need exact implementation comparison"}
                for index in range(3)
            ],
        },
    ))

    assert response.success is True
    assert len(response.result["approved_evidence"]) == 3


def test_agent_reputation_budget_expands_evidence_scope(tmp_path: Path):
    _seed_project(tmp_path)
    AgentProfileService(tmp_path).upsert_profile(AgentProfile(agent_id="lex", reputation_level="strategic", reputation_score=0.95))
    for index in range(3):
        (tmp_path / f"file_{index}.py").write_text("print('x')\n", encoding="utf-8")

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.request",
        session_id="thread-1",
        agent_id="lex",
        arguments={
            "project_id": "Ageix",
            "objective": "Review three files",
            "reason": "Need broad implementation comparison",
            "requested_evidence": [
                {"type": "file", "path": f"file_{index}.py", "reason": "Need exact implementation comparison"}
                for index in range(3)
            ],
        },
    ))

    assert response.success is True
    assert response.metadata["agent_reputation_level"] == "strategic"
