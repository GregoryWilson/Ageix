from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models.capability_request import CapabilityRequest
from models.evidence_access_proposal import EvidenceAccessProposal
from services.capability_audit_service import CapabilityAuditService
from services.capability_execution_service import CapabilityExecutionService
from services.evidence_access_proposal_service import EvidenceAccessProposalService
from services.evidence_broker_service import EvidenceBrokerService
from services.project_profile_service import ProjectProfileService


def _seed_project(tmp_path: Path, project_id: str = "Ageix") -> None:
    try:
        ProjectProfileService(tmp_path).register_project(project_id, project_id, "python", tmp_path)
    except Exception as exc:
        if "Project already registered" not in str(exc):
            raise


def _seed_mcp_exposure_files(tmp_path: Path) -> None:
    (tmp_path / "services" / "capabilities").mkdir(parents=True, exist_ok=True)
    (tmp_path / "web" / "routes").mkdir(parents=True, exist_ok=True)
    (tmp_path / "models").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ageix_mcp").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts" / "Smoke").mkdir(parents=True, exist_ok=True)

    (tmp_path / "services" / "capabilities" / "evidence_capabilities.py").write_text(
        "def register_capabilities(repo_root):\n    return [('evidence.request', evidence_request)]\n",
        encoding="utf-8",
    )
    (tmp_path / "web" / "routes" / "mcp_routes.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\ndef mcp_tools():\n    return {'tools': []}\n",
        encoding="utf-8",
    )
    (tmp_path / "models" / "capability_definition.py").write_text(
        "class CapabilityDefinition:\n    capability_id: str\n    handler: str\n",
        encoding="utf-8",
    )
    (tmp_path / "ageix_mcp" / "tool_registry.py").write_text(
        "class MCPToolRegistry:\n    def get(self, name):\n        return None\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_sprint_15_0_mcp_platform_foundation.py").write_text(
        "def test_mcp_capability_exposure():\n    assert True\n",
        encoding="utf-8",
    )
    (tmp_path / "scripts" / "Smoke" / "smoke_16_4_mcp_transport_bridge.py").write_text(
        "def main():\n    print('mcp smoke')\n",
        encoding="utf-8",
    )


def _approved_intent_plan(tmp_path: Path):
    _seed_project(tmp_path)
    _seed_mcp_exposure_files(tmp_path)
    decision = EvidenceAccessProposalService(tmp_path).evaluate(EvidenceAccessProposal(
        session_id="thread-17-1",
        agent_id="lex",
        project_id="Ageix",
        request_mode="intent",
        objective="Need to understand MCP capability exposure",
        reason="Need primary implementation, supporting registration, and validation evidence before designing the next MCP change.",
        target="MCP capability exposure evidence.request mcp routes registry tests",
        desired_outcome="Return a governed evidence package that satisfies the approved MCP exposure intent.",
        intent_type="architecture_review",
    ))
    assert decision.decision == "approved"
    assert decision.evidence_plan is not None
    return decision


def test_broker_returns_evidence_package_for_approved_plan(tmp_path: Path):
    decision = _approved_intent_plan(tmp_path)

    package = EvidenceBrokerService(tmp_path).request_evidence(
        proposal_id=decision.proposal_id,
        requester_identity={"session_id": "thread-17-1", "agent_id": "lex", "project_id": "Ageix"},
    )

    assert package.package_id.startswith("EVPKG-")
    assert package.proposal_id == decision.proposal_id
    assert package.evidence_plan_id == decision.evidence_plan.plan_id
    assert package.primary_evidence
    assert package.supporting_evidence
    assert package.validation_evidence
    assert package.retrieval_confidence >= 0.80
    assert "primary" in package.confidence_reason.lower()
    paths = [item.path for item in package.primary_evidence + package.supporting_evidence + package.validation_evidence]
    assert "web/routes/mcp_routes.py" in paths or "ageix_mcp/tool_registry.py" in paths
    assert any(path.startswith("tests/") or path.startswith("scripts/Smoke/") for path in paths)


def test_evidence_request_capability_fulfills_existing_plan_by_proposal_id(tmp_path: Path):
    decision = _approved_intent_plan(tmp_path)

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.request",
        session_id="thread-17-1",
        agent_id="lex",
        arguments={"project_id": "Ageix", "proposal_id": decision.proposal_id},
    ))

    assert response.success is True
    assert response.metadata["request_mode"] == "intent_package"
    assert response.result["package_id"].startswith("EVPKG-")
    assert response.result["primary_evidence"]
    assert response.result["supporting_evidence"]
    assert response.result["validation_evidence"]
    assert response.result["retrieval_confidence"] >= 0.80


def test_evidence_request_capability_fulfills_existing_plan_by_plan_id(tmp_path: Path):
    decision = _approved_intent_plan(tmp_path)

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.request",
        session_id="thread-17-1",
        agent_id="lex",
        arguments={"project_id": "Ageix", "evidence_plan_id": decision.evidence_plan.plan_id},
    ))

    assert response.success is True
    assert response.result["evidence_plan_id"] == decision.evidence_plan.plan_id


def test_broker_denies_unapproved_or_expired_plans(tmp_path: Path):
    _seed_project(tmp_path)
    _seed_mcp_exposure_files(tmp_path)
    decision = EvidenceAccessProposalService(tmp_path).evaluate(EvidenceAccessProposal(
        session_id="thread-17-1",
        agent_id="lex",
        project_id="Ageix",
        request_mode="intent",
        objective="Read the entire repository",
        reason="Need all files and everything in the whole repository.",
        target="entire repository",
        desired_outcome="Understand all source code.",
    ))

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.request",
        session_id="thread-17-1",
        agent_id="lex",
        arguments={"project_id": "Ageix", "proposal_id": decision.proposal_id},
    ))

    assert response.success is False
    assert response.error == "evidence_plan_not_approved"

    approved = _approved_intent_plan(tmp_path)
    persisted = tmp_path / ".ageix" / "manifests" / "evidence_access_proposals" / approved.proposal_id / "proposal.json"
    payload = json.loads(persisted.read_text(encoding="utf-8"))
    payload["decision"]["evidence_plan"]["expires_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    persisted.write_text(json.dumps(payload), encoding="utf-8")

    expired = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.request",
        session_id="thread-17-1",
        agent_id="lex",
        arguments={"project_id": "Ageix", "proposal_id": approved.proposal_id},
    ))

    assert expired.success is False
    assert expired.error == "evidence_plan_expired"


def test_evidence_package_persisted_and_audited(tmp_path: Path):
    decision = _approved_intent_plan(tmp_path)

    package = EvidenceBrokerService(tmp_path).request_evidence(
        proposal_id=decision.proposal_id,
        requester_identity={"session_id": "thread-17-1", "agent_id": "lex", "project_id": "Ageix", "client_id": "chatgpt"},
    )

    persisted = tmp_path / ".ageix" / "evidence_packages" / package.package_id / "package.json"
    assert persisted.exists()
    payload = json.loads(persisted.read_text(encoding="utf-8"))
    assert payload["audit_metadata"]["evidence_plan_id"] == decision.evidence_plan.plan_id
    assert payload["audit_metadata"]["evidence_retrieved"]
    assert payload["retrieval_confidence"] == package.retrieval_confidence

    records = CapabilityAuditService(tmp_path).list_records()
    broker_record = [record for record in records if record["reason"] == "evidence_package_retrieved"][-1]
    assert broker_record["metadata"]["intent"] == decision.evidence_plan.objective
    assert broker_record["metadata"]["evidence_retrieved"]
    assert broker_record["metadata"]["retrieval_confidence"] == package.retrieval_confidence


def test_explicit_evidence_request_still_uses_existing_behavior(tmp_path: Path):
    _seed_project(tmp_path)
    (tmp_path / "foo.py").write_text("def run():\n    return True\n", encoding="utf-8")

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.request",
        session_id="thread-17-1",
        agent_id="lex",
        arguments={
            "project_id": "Ageix",
            "objective": "Debug run function",
            "reason": "Need exact function implementation for focused debugging.",
            "request_mode": "explicit",
            "requested_evidence": [{
                "type": "symbol",
                "path": "foo.py",
                "symbol": "run",
                "reason": "Need exact function implementation for focused debugging.",
            }],
        },
    ))

    assert response.success is True
    assert response.metadata["request_mode"] == "explicit"
    assert "approved_evidence" in response.result
    assert "def run" in response.result["approved_evidence"][0]["content"]
