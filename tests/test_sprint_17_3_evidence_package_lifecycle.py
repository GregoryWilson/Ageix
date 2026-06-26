from __future__ import annotations

import json
from pathlib import Path

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.evidence_broker_service import EvidenceBrokerService
from services.evidence_package_index_service import EvidencePackageIndexService
from services.evidence_package_lifecycle_service import EvidencePackageLifecycleService
from tests.test_sprint_17_1_evidence_broker_package import _approved_intent_plan


def _items(package):
    return package.primary_evidence + package.supporting_evidence + package.validation_evidence


def _package(tmp_path: Path):
    decision = _approved_intent_plan(tmp_path)
    package = EvidenceBrokerService(tmp_path).request_evidence(
        proposal_id=decision.proposal_id,
        requester_identity={"session_id": "thread-17-3", "agent_id": "lex", "project_id": "Ageix", "client_id": "chatgpt"},
    )
    return decision, package


def test_package_list_returns_project_scoped_paginated_summaries(tmp_path: Path):
    decision, package = _package(tmp_path)

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.package.list",
        session_id="thread-17-3",
        agent_id="lex",
        arguments={"project_id": "Ageix", "limit": 1, "offset": 0, "objective_contains": "MCP capability"},
    ))

    assert response.success is True
    assert response.result["pagination"]["limit"] == 1
    assert response.result["pagination"]["returned"] == 1
    summary = response.result["packages"][0]
    assert summary["package_id"] == package.package_id
    assert summary["proposal_id"] == decision.proposal_id
    assert "primary_evidence" not in summary
    assert summary["project_id"] == "Ageix"


def test_context_search_filters_package_index_without_loading_contents(tmp_path: Path):
    _, package = _package(tmp_path)

    result = EvidencePackageLifecycleService(tmp_path).list_packages(
        requester_identity={"session_id": "thread-17-3", "agent_id": "lex", "project_id": "Ageix"},
        context_contains=package.evidence_plan_id[-6:],
    )

    assert result["pagination"]["total"] == 1
    assert result["packages"][0]["package_id"] == package.package_id


def test_package_details_returns_metadata_manifest_and_provenance_not_contents(tmp_path: Path):
    _, package = _package(tmp_path)

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.package.details",
        session_id="thread-17-3",
        agent_id="lex",
        arguments={"project_id": "Ageix", "package_id": package.package_id},
    ))

    assert response.success is True
    assert response.result["package_id"] == package.package_id
    assert response.result["repository_snapshot"]["generated_at"]
    assert response.result["evidence_counts"]["total_evidence_count"] == len(_items(package))
    assert response.result["provenance_summary"]["retrieval_methods"]
    manifest_item = response.result["evidence_manifest"][0]
    assert manifest_item["provenance"]["selection_reason"]
    assert "content" not in manifest_item


def test_freshness_runs_on_specific_package_and_updates_index(tmp_path: Path):
    _, package = _package(tmp_path)
    changed_path = _items(package)[0].path
    with open(tmp_path / changed_path, "a", encoding="utf-8") as handle:
        handle.write("\n# sprint 17.3 substantive drift\n")

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.package.freshness",
        session_id="thread-17-3",
        agent_id="lex",
        arguments={"project_id": "Ageix", "package_id": package.package_id},
    ))

    assert response.success is True
    assert response.result["package_id"] == package.package_id
    assert response.result["stale"] is True
    assert changed_path in response.result["changed_paths"]
    entry = [item for item in EvidencePackageIndexService(tmp_path).list_entries() if item["package_id"] == package.package_id][0]
    assert entry["stale"] is True
    assert entry["freshness_status"] == "modified"
    assert entry["last_freshness_check_at"]


def test_rehydrate_returns_specific_immutable_package_without_freshness_evaluation_or_mutation(tmp_path: Path):
    _, package = _package(tmp_path)
    persisted_path = tmp_path / ".ageix" / "evidence_packages" / package.package_id / "package.json"
    original_payload = json.loads(persisted_path.read_text(encoding="utf-8"))
    changed_path = _items(package)[0].path
    with open(tmp_path / changed_path, "a", encoding="utf-8") as handle:
        handle.write("\n# rehydrate should not freshness check\n")

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.package.rehydrate",
        session_id="thread-17-3",
        agent_id="lex",
        arguments={"project_id": "Ageix", "package_id": package.package_id},
    ))

    assert response.success is True
    assert response.metadata["freshness_evaluated"] is False
    assert response.result["package_id"] == package.package_id
    assert response.result.get("freshness") is None
    assert json.loads(persisted_path.read_text(encoding="utf-8")) == original_payload


def test_package_access_is_same_project_scoped(tmp_path: Path):
    _, package = _package(tmp_path)

    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id="evidence.package.details",
        session_id="thread-17-3-other",
        agent_id="lex",
        arguments={"project_id": "OtherProject", "package_id": package.package_id},
    ))

    assert response.success is False
    assert response.error == "evidence_package_project_scope_denied"


def test_mcp_discovery_exposes_package_lifecycle_tools(tmp_path: Path):
    from ageix_mcp.tool_registry import MCPToolRegistry

    registry = MCPToolRegistry()
    names = {tool.name for tool in registry.list_tools() if tool.category == "evidence"}

    assert "ageix.evidence.package.list" in names
    assert "ageix.evidence.package.details" in names
    assert "ageix.evidence.package.freshness" in names
    assert "ageix.evidence.package.rehydrate" in names
