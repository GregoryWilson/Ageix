from __future__ import annotations

import json
from pathlib import Path
from pprint import pprint

from models.capability_request import CapabilityRequest
from models.evidence_package import EvidencePackage
from services.capability_execution_service import CapabilityExecutionService
from services.evidence_package_cleanup_service import EvidencePackageCleanupService
from services.evidence_package_index_service import EvidencePackageIndexService

ROOT = Path(__file__).resolve().parents[2]


def _execute(service: CapabilityExecutionService, capability_id: str, arguments: dict, *, session_id: str = "smoke-17-5"):
    return service.execute(CapabilityRequest(
        capability_id=capability_id,
        session_id=session_id,
        agent_id="lex",
        arguments=arguments,
    ))


def _mark_smoke_demo(package_id: str) -> Path:
    package_path = ROOT / ".ageix" / "evidence_packages" / package_id / "package.json"
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    payload["lifecycle"] = {
        "artifact_type": "smoke_demo",
        "cleanup_eligible": True,
        "created_for_sprint": "17.5",
        "retention_policy": "manual_cleanup",
    }
    package_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    EvidencePackageIndexService(ROOT).upsert_package(EvidencePackage(**payload))
    return package_path


def main() -> int:
    print("== Smoke 17.5: evidence package operational polish ==")
    EvidencePackageIndexService(ROOT).rebuild_from_package_store()
    service = CapabilityExecutionService(ROOT)

    proposal = _execute(service, "evidence.proposal.submit", {
        "project_id": "Ageix",
        "request_mode": "intent",
        "objective": "Need to understand MCP capability exposure",
        "reason": "Need primary implementation, supporting registration, and validation evidence before validating package lifecycle operations.",
        "target": "MCP capability exposure evidence.request package lifecycle tests",
        "desired_outcome": "Create an inspectable smoke-demo evidence package for operational validation.",
        "intent_type": "architecture_review",
    })
    assert proposal.success, proposal.error

    package_response = _execute(service, "evidence.request", {
        "project_id": "Ageix",
        "proposal_id": proposal.result["proposal_id"],
    })
    assert package_response.success, package_response.error
    package_id = package_response.result["package_id"]
    package_path = _mark_smoke_demo(package_id)

    listed = _execute(service, "evidence.package.list", {
        "project_id": "Ageix",
        "limit": 10,
        "context_contains": package_id[-6:],
    })
    assert listed.success, listed.error
    assert any(item["package_id"] == package_id for item in listed.result["packages"])

    details = _execute(service, "evidence.package.details", {"project_id": "Ageix", "package_id": package_id})
    assert details.success, details.error
    assert details.result["evidence_counts"]["total_evidence_count"] > 0
    assert details.result["evidence_manifest"]
    assert "content" not in details.result["evidence_manifest"][0]

    freshness = _execute(service, "evidence.package.freshness", {"project_id": "Ageix", "package_id": package_id})
    assert freshness.success, freshness.error
    assert freshness.result["freshness_status"] in {"unchanged", "modified", "partially_missing", "missing"}

    recommendations = _execute(service, "evidence.package.recommend", {
        "project_id": "Ageix",
        "objective": "Need to understand MCP capability exposure",
        "limit": 5,
    })
    assert recommendations.success, recommendations.error
    assert any(item["package_id"] == package_id for item in recommendations.result["recommended_packages"])

    reuse = _execute(service, "evidence.package.reuse", {
        "project_id": "Ageix",
        "package_id": package_id,
        "reuse_reason": "Chair approved reuse during Sprint 17.5 operational smoke.",
    })
    assert reuse.success, reuse.error
    child_id = reuse.result["package_id"]
    child_path = _mark_smoke_demo(child_id)

    lineage = _execute(service, "evidence.package.lineage", {"project_id": "Ageix", "package_id": package_id})
    assert lineage.success, lineage.error
    assert any(item["package_id"] == child_id for item in lineage.result["children"])

    validation = EvidencePackageIndexService(ROOT).validate_index()
    assert validation["status"] == "pass", validation
    cleanup_preview = EvidencePackageCleanupService(ROOT).cleanup_smoke_demo_packages(dry_run=True)
    assert package_id in {item["package_id"] for item in cleanup_preview["candidates"]}
    assert child_id in {item["package_id"] for item in cleanup_preview["candidates"]}

    pprint({
        "package_store": "persistent",
        "parent_package_id": package_id,
        "parent_package_path": str(package_path.relative_to(ROOT)),
        "child_package_id": child_id,
        "child_package_path": str(child_path.relative_to(ROOT)),
        "cleanup_eligible": True,
        "cleanup_command_dry_run": "PYTHONPATH=. python scripts/Utilities/cleanup_smoke_evidence_packages.py --dry-run",
        "cleanup_command_execute": "PYTHONPATH=. python scripts/Utilities/cleanup_smoke_evidence_packages.py",
        "index_validation": validation,
    })
    print("Smoke 17.5 PASS: persistent smoke-demo package, discovery, details, freshness, recommendation, reuse, lineage, cleanup preview, and index validation verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
