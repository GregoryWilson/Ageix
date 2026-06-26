from __future__ import annotations

import json
from pathlib import Path

from models.capability_request import CapabilityRequest
from services.capability_audit_service import CapabilityAuditService
from services.capability_execution_service import CapabilityExecutionService
from services.evidence_broker_service import EvidenceBrokerService
from services.evidence_package_index_service import EvidencePackageIndexService
from tests.test_sprint_17_1_evidence_broker_package import _approved_intent_plan


def _package(tmp_path: Path, *, agent_id: str = "lex", client_id: str = "chatgpt"):
    decision = _approved_intent_plan(tmp_path)
    package = EvidenceBrokerService(tmp_path).request_evidence(
        proposal_id=decision.proposal_id,
        requester_identity={"session_id": "thread-17-6", "agent_id": agent_id, "project_id": "Ageix", "client_id": client_id},
    )
    return package


def _execute(tmp_path: Path, capability_id: str, arguments: dict, *, agent_id: str = "lex"):
    return CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id=capability_id,
        session_id="thread-17-6",
        agent_id=agent_id,
        arguments=arguments,
    ))


def _args(**extra):
    base = {"project_id": "Ageix", "client_id": "chatgpt"}
    base.update(extra)
    return base


def _entry(tmp_path: Path, package_id: str) -> dict:
    return [item for item in EvidencePackageIndexService(tmp_path).list_entries() if item["package_id"] == package_id][0]


def test_usage_metrics_increment_on_recommend_reuse_and_freshness(tmp_path: Path):
    package = _package(tmp_path)

    rec = _execute(tmp_path, "evidence.package.recommend", _args(objective="Need MCP capability exposure evidence"))
    fresh = _execute(tmp_path, "evidence.package.freshness", _args(package_id=package.package_id))
    reuse = _execute(tmp_path, "evidence.package.reuse", _args(package_id=package.package_id, reuse_reason="Chair approved reuse."))

    assert rec.success is True
    assert fresh.success is True
    assert reuse.success is True
    entry = _entry(tmp_path, package.package_id)
    assert entry["recommendation_count"] == 1
    assert entry["last_recommended_at"]
    assert entry["freshness_check_count"] == 1
    assert entry["last_freshness_check_at"]
    assert entry["reused_count"] == 1
    assert entry["last_reused_at"]


def test_deprecated_package_is_rehydratable_but_not_preferred(tmp_path: Path):
    package = _package(tmp_path)
    before = (tmp_path / ".ageix" / "evidence_packages" / package.package_id / "package.json").read_text(encoding="utf-8")

    dep = _execute(tmp_path, "evidence.package.deprecate", _args(package_id=package.package_id, reason="Old package should not be preferred."))
    rec = _execute(tmp_path, "evidence.package.recommend", _args(objective="Need MCP capability exposure evidence"))
    rehydrate = _execute(tmp_path, "evidence.package.rehydrate", _args(package_id=package.package_id))
    after = (tmp_path / ".ageix" / "evidence_packages" / package.package_id / "package.json").read_text(encoding="utf-8")

    assert dep.success is True
    assert dep.result["new_governance_state"]["status"] == "deprecated"
    assert rec.success is True
    assert rec.result["recommended_packages"] == []
    assert rehydrate.success is True
    assert rehydrate.result["package_id"] == package.package_id
    assert before == after


def test_superseded_package_points_to_newer_replacement_and_recommendation_prefers_visible_replacement(tmp_path: Path):
    old = _package(tmp_path)
    new = _package(tmp_path)
    # Keep objective-family compatibility explicit for deterministic validation.
    new_path = tmp_path / ".ageix" / "evidence_packages" / new.package_id / "package.json"
    payload = json.loads(new_path.read_text(encoding="utf-8"))
    payload["objective"] = old.objective + " replacement"
    new_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    newer_package = EvidenceBrokerService(tmp_path).load_package(new.package_id, requester_identity=_args(), evaluate_freshness=False)
    EvidencePackageIndexService(tmp_path).upsert_package(newer_package)

    supersede = _execute(tmp_path, "evidence.package.supersede", _args(
        package_id=old.package_id,
        superseded_by_package_id=new.package_id,
        reason="Replacement package has newer governed evidence.",
    ))
    rec = _execute(tmp_path, "evidence.package.recommend", _args(objective="Need MCP capability exposure evidence"))
    ids = [item["package_id"] for item in rec.result["recommended_packages"]]
    old_item = [item for item in rec.result["recommended_packages"] if item["package_id"] == old.package_id][0]

    assert supersede.success is True
    assert supersede.result["superseded_by_package_id"] == new.package_id
    assert ids.index(new.package_id) < ids.index(old.package_id)
    assert old_item["governance_status"] == "superseded"
    assert old_item["superseded_by_package_id"] == new.package_id
    assert old_item["better_replacement_exists"] is True
    assert old_item["better_replacement_visible"] is True


def test_governance_status_appears_in_summary_details_and_audit(tmp_path: Path):
    package = _package(tmp_path)
    _execute(tmp_path, "evidence.package.deprecate", _args(package_id=package.package_id, reason="Governance smoke deprecation."))

    listed = _execute(tmp_path, "evidence.package.list", _args())
    details = _execute(tmp_path, "evidence.package.details", _args(package_id=package.package_id))
    audit = CapabilityAuditService(tmp_path).list_records()[-20:]
    reasons = {record["reason"] for record in audit}

    assert listed.success is True
    assert listed.result["packages"][0]["governance"]["status"] == "deprecated"
    assert details.success is True
    assert details.result["governance_status"] == "deprecated"
    assert details.result["deprecated"] is True
    assert "package_deprecated" in reasons


def test_mcp_discovery_exposes_package_governance_tools(tmp_path: Path):
    from ageix_mcp.tool_registry import MCPToolRegistry

    names = {tool.name for tool in MCPToolRegistry().list_tools() if tool.category == "evidence"}

    assert "ageix.evidence.package.deprecate" in names
    assert "ageix.evidence.package.supersede" in names
