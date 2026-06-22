from __future__ import annotations

from pathlib import Path

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.evidence_broker_service import EvidenceBrokerService
from services.evidence_package_index_service import EvidencePackageIndexService
from tests.test_sprint_17_1_evidence_broker_package import _approved_intent_plan


def _package(tmp_path: Path, *, agent_id: str = "lex", client_id: str = "chatgpt"):
    decision = _approved_intent_plan(tmp_path)
    package = EvidenceBrokerService(tmp_path).request_evidence(
        proposal_id=decision.proposal_id,
        requester_identity={"session_id": "thread-17-4", "agent_id": agent_id, "project_id": "Ageix", "client_id": client_id},
    )
    return decision, package


def _execute(tmp_path: Path, capability_id: str, arguments: dict, *, agent_id: str = "lex"):
    return CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id=capability_id,
        session_id="thread-17-4",
        agent_id=agent_id,
        arguments=arguments,
    ))


def test_package_recommendation_is_visibility_filtered_and_advisory(tmp_path: Path):
    _, package = _package(tmp_path, agent_id="lex", client_id="chatgpt")

    lex = _execute(tmp_path, "evidence.package.recommend", {
        "project_id": "Ageix",
        "client_id": "chatgpt",
        "objective": "Need to understand MCP capability exposure",
    })

    assert lex.success is True
    assert lex.result["governance"]["chair_authority_required"] is True
    assert lex.result["governance"]["automatic_reuse"] is False
    assert lex.result["recommended_packages"][0]["package_id"] == package.package_id

    gemini = _execute(tmp_path, "evidence.package.recommend", {
        "project_id": "Ageix",
        "client_id": "gemini",
        "objective": "Need to understand MCP capability exposure",
    }, agent_id="gemini")

    assert gemini.success is True
    assert gemini.result["recommended_packages"] == []


def test_reuse_creates_new_immutable_child_package_and_updates_parent_index(tmp_path: Path):
    _, parent = _package(tmp_path)

    response = _execute(tmp_path, "evidence.package.reuse", {
        "project_id": "Ageix",
        "client_id": "chatgpt",
        "package_id": parent.package_id,
        "objective": "Reuse prior MCP capability exposure evidence",
        "reuse_reason": "Chair approved reuse after package recommendation.",
        "lineage_type": "reuse",
    })

    assert response.success is True
    child = response.result
    assert child["package_id"] != parent.package_id
    assert child["parent_package_ids"] == [parent.package_id]
    assert child["lineage_type"] == "reuse"
    assert child["reuse_reason"] == "Chair approved reuse after package recommendation."
    assert child["primary_evidence"] == [item.model_dump() for item in parent.primary_evidence]

    parent_path = tmp_path / ".ageix" / "evidence_packages" / parent.package_id / "package.json"
    child_path = tmp_path / ".ageix" / "evidence_packages" / child["package_id"] / "package.json"
    assert parent_path.exists()
    assert child_path.exists()

    parent_entry = [item for item in EvidencePackageIndexService(tmp_path).list_entries() if item["package_id"] == parent.package_id][0]
    child_entry = [item for item in EvidencePackageIndexService(tmp_path).list_entries() if item["package_id"] == child["package_id"]][0]
    assert parent_entry["reused_count"] == 1
    assert parent_entry["last_reused_at"]
    assert child_entry["parent_package_ids"] == [parent.package_id]


def test_lineage_returns_visible_parents_children_ancestors_and_descendants(tmp_path: Path):
    _, parent = _package(tmp_path)
    child_response = _execute(tmp_path, "evidence.package.reuse", {
        "project_id": "Ageix",
        "client_id": "chatgpt",
        "package_id": parent.package_id,
        "reuse_reason": "Chair approved reuse for lineage validation.",
    })
    child_id = child_response.result["package_id"]

    parent_lineage = _execute(tmp_path, "evidence.package.lineage", {
        "project_id": "Ageix",
        "client_id": "chatgpt",
        "package_id": parent.package_id,
    })
    child_lineage = _execute(tmp_path, "evidence.package.lineage", {
        "project_id": "Ageix",
        "client_id": "chatgpt",
        "package_id": child_id,
    })

    assert parent_lineage.success is True
    assert parent_lineage.result["children"][0]["package_id"] == child_id
    assert parent_lineage.result["descendants"][0]["package_id"] == child_id
    assert child_lineage.result["parents"][0]["package_id"] == parent.package_id
    assert child_lineage.result["ancestors"][0]["package_id"] == parent.package_id


def test_reuse_denies_cross_requester_package_visibility(tmp_path: Path):
    _, parent = _package(tmp_path, agent_id="lex", client_id="chatgpt")

    response = _execute(tmp_path, "evidence.package.reuse", {
        "project_id": "Ageix",
        "client_id": "gemini",
        "package_id": parent.package_id,
        "reuse_reason": "Gemini should not reuse Lex-scoped package.",
    }, agent_id="gemini")

    assert response.success is False
    assert response.error == "evidence_package_visibility_denied"


def test_automatic_refresh_is_rejected_because_refresh_must_create_new_governed_package(tmp_path: Path):
    _, parent = _package(tmp_path)

    response = _execute(tmp_path, "evidence.package.reuse", {
        "project_id": "Ageix",
        "client_id": "chatgpt",
        "package_id": parent.package_id,
        "automatic_refresh": True,
    })

    assert response.success is False
    assert response.error == "automatic_refresh_not_allowed"


def test_mcp_discovery_exposes_reuse_and_lineage_tools(tmp_path: Path):
    from ageix_mcp.tool_registry import MCPToolRegistry

    registry = MCPToolRegistry()
    names = {tool.name for tool in registry.list_tools() if tool.category == "evidence"}

    assert "ageix.evidence.package.recommend" in names
    assert "ageix.evidence.package.reuse" in names
    assert "ageix.evidence.package.lineage" in names
