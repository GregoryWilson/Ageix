from __future__ import annotations

from pathlib import Path
from pprint import pprint

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.project_profile_service import ProjectProfileService
from services.project_registry_service import ProjectRegistryError


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    try:
        ProjectProfileService(repo).register_project(
            "Ageix_Test",
            "Ageix Test",
            "python",
            repo,
            metadata={"purpose": "Sprint 17.0 intent evidence planning smoke"},
        )
    except ProjectRegistryError:
        pass
    service = CapabilityExecutionService(repo)

    print("\n== Smoke 17.0: Intent-governed evidence planning ==")

    intent_response = service.execute(CapabilityRequest(
        capability_id="evidence.proposal.submit",
        session_id="smoke-17-0-intent",
        agent_id="lex",
        arguments={
            "project_id": "Ageix_Test",
            "request_mode": "intent",
            "objective": "Design MCP evidence request adapter support",
            "reason": "Need to understand existing MCP capability exposure architecture before proposing the feature design.",
            "target": "evidence capability adapter",
            "desired_outcome": "Produce a Sprint 17 implementation plan for intent-governed evidence planning.",
            "intent_type": "feature_design",
        },
    ))
    print("\n-- intent proposal --")
    pprint(intent_response.model_dump())
    assert intent_response.success is True
    assert intent_response.metadata["request_mode"] == "intent"
    assert intent_response.result["approved_evidence"] == []
    assert intent_response.result["evidence_plan"]["plan_id"].startswith("EVP-")
    assert 0.70 <= intent_response.result["evidence_plan"]["planning_confidence"] < 1.0
    assert all(not target["target"].endswith((".patch", ".zip", ".diff")) for target in intent_response.result["evidence_plan"]["resolved_targets"])
    assert intent_response.result["metadata"]["source_files_returned"] is False

    repo_walk_response = service.execute(CapabilityRequest(
        capability_id="evidence.proposal.submit",
        session_id="smoke-17-0-intent",
        agent_id="lex",
        arguments={
            "project_id": "Ageix_Test",
            "request_mode": "intent",
            "objective": "Read the entire repository",
            "reason": "Need all files and everything in the whole repository.",
            "target": "entire repository",
            "desired_outcome": "Understand all source code.",
        },
    ))
    print("\n-- repo walk denial --")
    pprint(repo_walk_response.model_dump())
    assert repo_walk_response.success is False
    assert repo_walk_response.error == "denied"
    assert "intent_request_contains_repo_walk_language" in repo_walk_response.result["reasons"]
    assert repo_walk_response.result["evidence_plan"]["resolved_targets"] == []
    assert repo_walk_response.result["evidence_plan"]["evidence_needed"] == []

    explicit_response = service.execute(CapabilityRequest(
        capability_id="evidence.request",
        session_id="smoke-17-0-explicit",
        agent_id="lex",
        arguments={
            "project_id": "Ageix_Test",
            "request_mode": "explicit",
            "objective": "Review evidence capability implementation",
            "reason": "Need exact file implementation for focused debugging review.",
            "requested_evidence": [{
                "type": "file",
                "path": "services/capabilities/evidence_capabilities.py",
                "reason": "Need exact file implementation for focused debugging review.",
            }],
        },
    ))
    print("\n-- explicit request still works --")
    pprint({
        "success": explicit_response.success,
        "error": explicit_response.error,
        "request_mode": explicit_response.metadata.get("request_mode"),
        "approved_count": len(explicit_response.result.get("approved_evidence", [])) if isinstance(explicit_response.result, dict) else None,
    })
    assert explicit_response.success is True
    assert explicit_response.metadata["request_mode"] == "explicit"
    assert "register_capabilities" in explicit_response.result["approved_evidence"][0]["content"]

    print("\nSmoke 17.0 PASS: intent evidence planning added while explicit file evidence remains intact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
