from __future__ import annotations

import json
from pathlib import Path

from models.capability_request import CapabilityRequest
from services.capability_audit_service import CapabilityAuditService
from services.capability_execution_service import CapabilityExecutionService
from services.decision_trace_service import DecisionTraceService
from services.evidence_broker_service import EvidenceBrokerService
from services.evidence_package_index_service import EvidencePackageIndexService
from tests.test_sprint_17_1_evidence_broker_package import _approved_intent_plan


def _package(tmp_path: Path):
    decision = _approved_intent_plan(tmp_path)
    package = EvidenceBrokerService(tmp_path).request_evidence(
        proposal_id=decision.proposal_id,
        requester_identity={"session_id": "thread-17-7", "agent_id": "lex", "project_id": "Ageix", "client_id": "chatgpt"},
    )
    return decision, package


def _execute(tmp_path: Path, capability_id: str, arguments: dict):
    base = {"project_id": "Ageix", "client_id": "chatgpt"}
    base.update(arguments)
    return CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id=capability_id,
        session_id="thread-17-7",
        agent_id="lex",
        arguments=base,
    ))


def _entry(tmp_path: Path, package_id: str) -> dict:
    return [item for item in EvidencePackageIndexService(tmp_path).list_entries() if item["package_id"] == package_id][0]


def test_chair_creates_append_only_decision_trace_with_evidence_package_links(tmp_path: Path):
    decision, package = _package(tmp_path)

    response = _execute(tmp_path, "decision.trace.create", {
        "decision_summary": "Approve MCP evidence package governance direction.",
        "outcome": "approved",
        "proposal_id": decision.proposal_id,
        "evidence_package_ids": [package.package_id],
        "reason": "Chair approved based on package evidence.",
        "repository_snapshot": {"git_commit": "abc123"},
    })

    assert response.success is True
    trace = response.result
    assert trace["trace_id"].startswith("TRACE-")
    assert trace["proposal_id"] == decision.proposal_id
    assert trace["evidence_package_ids"] == [package.package_id]
    assert trace["outcome"] == "approved"
    assert (tmp_path / ".ageix" / "decision_traces" / trace["trace_id"] / "trace.json").exists()

    persisted = json.loads((tmp_path / ".ageix" / "decision_traces" / trace["trace_id"] / "trace.json").read_text(encoding="utf-8"))
    assert persisted == trace


def test_all_initial_outcomes_are_supported_with_future_outcome_metadata_hook(tmp_path: Path):
    _, package = _package(tmp_path)
    outcomes = ["approved", "rejected", "implemented", "superseded", "abandoned", "deferred", "backlog"]

    for outcome in outcomes:
        response = _execute(tmp_path, "decision.trace.create", {
            "decision_summary": f"Decision was {outcome}.",
            "outcome": outcome,
            "evidence_package_ids": [package.package_id],
            "outcome_metadata": {"backlog_id": "BACKLOG-1" if outcome == "backlog" else None, "deferred_until": None},
        })
        assert response.success is True
        assert response.result["outcome"] == outcome
        assert "outcome_metadata" in response.result


def test_decision_trace_retrieval_reports_current_package_freshness_without_mutating_package(tmp_path: Path):
    _, package = _package(tmp_path)
    package_path = tmp_path / ".ageix" / "evidence_packages" / package.package_id / "package.json"
    before = package_path.read_text(encoding="utf-8")
    changed_path = (package.primary_evidence + package.supporting_evidence + package.validation_evidence)[0].path
    with open(tmp_path / changed_path, "a", encoding="utf-8") as handle:
        handle.write("\n# sprint 17.7 freshness drift\n")

    created = _execute(tmp_path, "decision.trace.create", {
        "decision_summary": "Implemented package-backed decision.",
        "outcome": "implemented",
        "evidence_package_ids": [package.package_id],
    })
    details = _execute(tmp_path, "decision.trace.get", {"trace_id": created.result["trace_id"]})
    after = package_path.read_text(encoding="utf-8")

    assert details.success is True
    linked = details.result["evidence_packages"][0]
    assert linked["package_id"] == package.package_id
    assert linked["current_freshness"]["stale"] is True
    assert changed_path in linked["current_freshness"]["changed_paths"]
    assert before == after


def test_decision_trace_list_and_package_history_discovery(tmp_path: Path):
    decision, package = _package(tmp_path)
    first = _execute(tmp_path, "decision.trace.create", {
        "decision_summary": "Backlog MCP evidence access decision.",
        "outcome": "backlog",
        "proposal_id": decision.proposal_id,
        "evidence_package_ids": [package.package_id],
    })

    by_outcome = _execute(tmp_path, "decision.trace.list", {"outcome": "backlog"})
    by_proposal = _execute(tmp_path, "decision.trace.list", {"proposal_id": decision.proposal_id})
    history = _execute(tmp_path, "decision.trace.package_history", {"package_id": package.package_id})

    assert by_outcome.success is True
    assert by_outcome.result["traces"][0]["trace_id"] == first.result["trace_id"]
    assert by_proposal.result["traces"][0]["proposal_id"] == decision.proposal_id
    assert history.success is True
    assert history.result["trace_count"] == 1
    assert history.result["traces"][0]["evidence_package_ids"] == [package.package_id]


def test_evidence_package_index_tracks_decision_usage_and_trace_audit(tmp_path: Path):
    _, package = _package(tmp_path)

    response = _execute(tmp_path, "decision.trace.create", {
        "decision_summary": "Approve historical evidence traceability.",
        "outcome": "approved",
        "evidence_package_ids": [package.package_id],
    })

    assert response.success is True
    entry = _entry(tmp_path, package.package_id)
    assert entry["used_in_decision_count"] == 1
    assert entry["last_used_in_decision_at"]
    reasons = {record["reason"] for record in CapabilityAuditService(tmp_path).list_records()[-10:]}
    assert "decision_trace_created" in reasons


def test_decision_trace_model_keeps_extensible_related_entities_without_architecture_fields(tmp_path: Path):
    _, package = _package(tmp_path)

    response = _execute(tmp_path, "decision.trace.create", {
        "decision_summary": "Deferred decision with future link placeholder.",
        "outcome": "deferred",
        "evidence_package_ids": [package.package_id],
        "related_entities": {"future_architecture_node": ["ARCH-NOT-YET"]},
        "metadata": {"extension_surface": "17.7"},
    })

    assert response.success is True
    assert response.result["related_entities"] == {"future_architecture_node": ["ARCH-NOT-YET"]}
    assert "architecture_node_ids" not in response.result


def test_mcp_discovery_exposes_decision_trace_tools(tmp_path: Path):
    from ageix_mcp.tool_registry import MCPToolRegistry

    names = {tool.name for tool in MCPToolRegistry().list_tools() if tool.category == "decision_trace"}

    assert "ageix.decision.trace.create" in names
    assert "ageix.decision.trace.get" in names
    assert "ageix.decision.trace.list" in names
    assert "ageix.decision.trace.package_history" in names
