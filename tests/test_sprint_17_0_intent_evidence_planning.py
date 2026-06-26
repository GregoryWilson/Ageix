from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from models.capability_request import CapabilityRequest
from models.evidence_access_proposal import EvidenceAccessProposal
from services.capability_execution_service import CapabilityExecutionService
from services.evidence_access_proposal_service import EvidenceAccessProposalService
from services.project_profile_service import ProjectProfileService


def _seed_project(tmp_path: Path, project_id: str = "Ageix") -> None:
    ProjectProfileService(tmp_path).register_project(project_id, project_id, "python", tmp_path)


def _seed_mcp_files(tmp_path: Path) -> None:
    (tmp_path / "services" / "capabilities").mkdir(parents=True)
    (tmp_path / "web" / "routes").mkdir(parents=True)
    (tmp_path / "models").mkdir(parents=True)
    (tmp_path / "tests").mkdir(parents=True)
    (tmp_path / "services" / "capabilities" / "evidence_capabilities.py").write_text("def register_capabilities():\n    pass\n", encoding="utf-8")
    (tmp_path / "services" / "capability_execution_service.py").write_text("class CapabilityExecutionService:\n    pass\n", encoding="utf-8")
    (tmp_path / "web" / "routes" / "mcp_routes.py").write_text("def mcp():\n    pass\n", encoding="utf-8")
    (tmp_path / "models" / "capability_definition.py").write_text("class CapabilityDefinition:\n    pass\n", encoding="utf-8")
    (tmp_path / "tests" / "test_sprint_15_0_mcp_capabilities.py").write_text("def test_mcp():\n    assert True\n", encoding="utf-8")


def test_intent_evidence_proposal_creates_plan_without_returning_source(tmp_path: Path):
    _seed_project(tmp_path)
    _seed_mcp_files(tmp_path)

    proposal = EvidenceAccessProposal(
        session_id="thread-17",
        agent_id="lex",
        project_id="Ageix",
        request_mode="intent",
        objective="Design MCP evidence request adapter support",
        reason="Need to understand existing MCP capability exposure architecture before proposing the feature design.",
        target="evidence capability adapter",
        desired_outcome="Produce a Sprint 17 implementation plan for intent-governed evidence planning.",
        intent_type="feature_design",
    )

    decision = EvidenceAccessProposalService(tmp_path).evaluate(proposal)

    assert decision.decision == "approved"
    assert decision.approved_evidence == []
    assert decision.evidence_plan is not None
    assert decision.evidence_plan.request_mode == "intent"
    assert decision.evidence_plan.intent_type == "feature_design"
    assert 0.70 <= decision.evidence_plan.planning_confidence < 1.0
    assert decision.evidence_plan.resolved_targets
    assert all(not target.target.endswith((".patch", ".zip", ".diff")) for target in decision.evidence_plan.resolved_targets)
    assert decision.metadata["source_files_returned"] is False
    assert decision.metadata["request_mode"] == "intent"
    expires_at = datetime.fromisoformat(str(decision.evidence_plan.expires_at))
    assert expires_at > datetime.now(timezone.utc)


def test_intent_evidence_proposal_denies_repo_walk_language(tmp_path: Path):
    _seed_project(tmp_path)
    _seed_mcp_files(tmp_path)

    decision = EvidenceAccessProposalService(tmp_path).evaluate(EvidenceAccessProposal(
        session_id="thread-17",
        agent_id="lex",
        project_id="Ageix",
        request_mode="intent",
        objective="Read the entire repository",
        reason="Need all files and everything in the whole repository.",
        target="entire repository",
        desired_outcome="Understand all source code.",
    ))

    assert decision.decision == "denied"
    assert "intent_request_contains_repo_walk_language" in decision.reasons
    assert decision.evidence_plan is not None
    assert decision.evidence_plan.planning_confidence < 0.45
    assert decision.evidence_plan.resolved_targets == []
    assert decision.evidence_plan.evidence_needed == []


def test_intent_evidence_proposal_escalates_low_confidence_request(tmp_path: Path):
    _seed_project(tmp_path)

    decision = EvidenceAccessProposalService(tmp_path).evaluate(EvidenceAccessProposal(
        session_id="thread-17",
        agent_id="lex",
        project_id="Ageix",
        request_mode="intent",
        objective="Review something useful",
        reason="Need more context before proceeding safely.",
        target="unclear target that does not resolve",
        desired_outcome="A better plan.",
    ))

    assert decision.decision == "human_approval_required"
    assert decision.human_approval_required is True
    assert decision.metadata["approval_id"].startswith("APR-")
    assert decision.evidence_plan is not None
    assert decision.evidence_plan.coverage_gaps


def test_explicit_evidence_request_path_still_returns_file_contents(tmp_path: Path):
    _seed_project(tmp_path)
    (tmp_path / "foo.py").write_text("def run():\n    return True\n", encoding="utf-8")

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.request",
        session_id="thread-17",
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
    assert "def run" in response.result["approved_evidence"][0]["content"]


def test_intent_evidence_capability_returns_plan_through_mcp_capability(tmp_path: Path):
    _seed_project(tmp_path)
    _seed_mcp_files(tmp_path)

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.proposal.submit",
        session_id="thread-17",
        agent_id="lex",
        arguments={
            "project_id": "Ageix",
            "request_mode": "intent",
            "objective": "Design MCP evidence request adapter support",
            "reason": "Need to understand existing MCP capability exposure architecture before proposing the feature design.",
            "target": "evidence capability adapter",
            "desired_outcome": "Produce a Sprint 17 implementation plan for intent-governed evidence planning.",
            "intent_type": "feature_design",
        },
    ))

    assert response.success is True
    assert response.metadata["proposal_type"] == "evidence_access"
    assert response.metadata["request_mode"] == "intent"
    assert 0.70 <= response.result["evidence_plan"]["planning_confidence"] < 1.0
    assert response.result["approved_evidence"] == []


def test_intent_planner_filters_generated_patch_artifacts(tmp_path: Path):
    _seed_project(tmp_path)
    _seed_mcp_files(tmp_path)
    (tmp_path / "ageix_sprint_17_0_intent_evidence_planning.patch").write_text("diff --git a/example b/example\n", encoding="utf-8")
    (tmp_path / "ageix_repo_sprint-17.0.zip").write_text("not a real zip for test purposes", encoding="utf-8")

    decision = EvidenceAccessProposalService(tmp_path).evaluate(EvidenceAccessProposal(
        session_id="thread-17",
        agent_id="lex",
        project_id="Ageix",
        request_mode="intent",
        objective="Design MCP evidence request adapter support",
        reason="Need to understand existing MCP capability exposure architecture before proposing the feature design.",
        target="evidence capability adapter",
        desired_outcome="Produce a Sprint 17 implementation plan for intent-governed evidence planning.",
        intent_type="feature_design",
    ))

    assert decision.evidence_plan is not None
    targets = [target.target for target in decision.evidence_plan.resolved_targets]
    assert "ageix_sprint_17_0_intent_evidence_planning.patch" not in targets
    assert "ageix_repo_sprint-17.0.zip" not in targets


def test_intent_evidence_decision_is_persisted_with_plan(tmp_path: Path):
    _seed_project(tmp_path)
    _seed_mcp_files(tmp_path)

    decision = EvidenceAccessProposalService(tmp_path).evaluate(EvidenceAccessProposal(
        session_id="thread-17",
        agent_id="lex",
        project_id="Ageix",
        request_mode="intent",
        objective="Design MCP evidence request adapter support",
        reason="Need to understand existing MCP capability exposure architecture before proposing the feature design.",
        target="evidence capability adapter",
        desired_outcome="Produce a Sprint 17 implementation plan for intent-governed evidence planning.",
        intent_type="feature_design",
    ))

    persisted = tmp_path / ".ageix" / "manifests" / "evidence_access_proposals" / decision.proposal_id / "proposal.json"
    payload = json.loads(persisted.read_text(encoding="utf-8"))
    assert payload["proposal"]["request_mode"] == "intent"
    assert payload["decision"]["evidence_plan"]["plan_id"].startswith("EVP-")
    assert payload["decision"]["metadata"]["source_files_returned"] is False
