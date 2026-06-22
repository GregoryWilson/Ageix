from __future__ import annotations

import json
from pathlib import Path
from pprint import pprint

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from models.evidence_package import EvidencePackage
from services.evidence_package_index_service import EvidencePackageIndexService

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    print("== Smoke 17.1: governed evidence broker package retrieval ==")
    execution = CapabilityExecutionService(ROOT)

    proposal = execution.execute(CapabilityRequest(
        capability_id="evidence.proposal.submit",
        session_id="smoke-17-1-session",
        agent_id="lex",
        arguments={
            "project_id": "Ageix",
            "request_mode": "intent",
            "objective": "Need to understand MCP capability exposure",
            "reason": "Need primary implementation, supporting registration, and validation evidence before designing the next MCP change.",
            "target": "MCP capability exposure evidence.request mcp routes registry tests",
            "desired_outcome": "Return a governed evidence package that satisfies the approved MCP exposure intent.",
            "intent_type": "architecture_review",
        },
    ))
    pprint({"proposal_success": proposal.success, "metadata": proposal.metadata})
    if not proposal.success:
        return 1

    package = execution.execute(CapabilityRequest(
        capability_id="evidence.request",
        session_id="smoke-17-1-session",
        agent_id="lex",
        arguments={"project_id": "Ageix", "proposal_id": proposal.result["proposal_id"]},
    ))
    result = package.result
    package_path = ROOT / ".ageix" / "evidence_packages" / str(result.get("package_id")) / "package.json"
    if package.success and package_path.exists():
        payload = json.loads(package_path.read_text(encoding="utf-8"))
        payload["lifecycle"] = {
            "artifact_type": "smoke_demo",
            "cleanup_eligible": True,
            "created_for_sprint": "17.5",
            "retention_policy": "manual_cleanup",
        }
        package_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        EvidencePackageIndexService(ROOT).upsert_package(EvidencePackage(**payload))

    pprint({
        "package_success": package.success,
        "package_id": result.get("package_id"),
        "retrieval_confidence": result.get("retrieval_confidence"),
        "primary": [item["path"] for item in result.get("primary_evidence", [])[:5]],
        "supporting": [item["path"] for item in result.get("supporting_evidence", [])[:5]],
        "validation": [item["path"] for item in result.get("validation_evidence", [])[:5]],
        "coverage_gaps": result.get("coverage_gaps"),
        "package_store": "persistent",
        "package_path": str(package_path.relative_to(ROOT)) if package_path.exists() else None,
        "cleanup_eligible": True if package_path.exists() else None,
    })
    return 0 if package.success and result.get("primary_evidence") else 1


if __name__ == "__main__":
    raise SystemExit(main())
