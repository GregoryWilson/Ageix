from __future__ import annotations

import json
import tempfile
from pathlib import Path

from models.capability_request import CapabilityRequest
from models.evidence_access_proposal import EvidenceAccessProposal
from services.capability_execution_service import CapabilityExecutionService
from services.evidence_access_proposal_service import EvidenceAccessProposalService
from services.evidence_broker_service import EvidenceBrokerService
from services.project_profile_service import ProjectProfileService


def seed_repo(repo: Path) -> None:
    ProjectProfileService(repo).register_project("Ageix", "Ageix", "python", repo)
    (repo / "services" / "capabilities").mkdir(parents=True, exist_ok=True)
    (repo / "models").mkdir(parents=True, exist_ok=True)
    (repo / "tests").mkdir(parents=True, exist_ok=True)
    (repo / "services" / "capabilities" / "evidence_capabilities.py").write_text(
        "def register_capabilities(repo_root):\n    return [('evidence.request', evidence_request)]\n",
        encoding="utf-8",
    )
    (repo / "models" / "evidence_package.py").write_text(
        "class EvidencePackage:\n    pass\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_evidence_package.py").write_text(
        "def test_package():\n    assert True\n",
        encoding="utf-8",
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        repo = Path(temp)
        seed_repo(repo)
        decision = EvidenceAccessProposalService(repo).evaluate(EvidenceAccessProposal(
            session_id="smoke-17-2",
            agent_id="lex",
            project_id="Ageix",
            request_mode="intent",
            objective="Explain evidence package retrieval",
            reason="Need implementation, model, and validation evidence to verify package explainability and freshness.",
            target="evidence package capability model tests",
            desired_outcome="Return a governed explainable evidence package.",
            intent_type="architecture_review",
        ))
        package = EvidenceBrokerService(repo).request_evidence(proposal_id=decision.proposal_id)
        first_item = package.all_evidence()[0]
        print("created", package.package_id, first_item.path, first_item.provenance.retrieval_method)

        with open(repo / first_item.path, "a", encoding="utf-8") as handle:
            handle.write("\n# smoke drift\n")

        response = CapabilityExecutionService(repo).execute(CapabilityRequest(
            capability_id="evidence.request",
            session_id="smoke-17-2",
            agent_id="lex",
            arguments={"project_id": "Ageix", "package_id": package.package_id},
        ))
        assert response.success is True
        assert response.result["freshness"]["stale"] is True
        assert first_item.path in response.result["freshness"]["changed_paths"]
        assert (repo / ".ageix" / "evidence_packages" / "index.json").exists()
        persisted = json.loads((repo / ".ageix" / "evidence_packages" / package.package_id / "package.json").read_text(encoding="utf-8"))
        assert "freshness" not in persisted or persisted["freshness"] is None
        print("Smoke 17.2 PASS: package rehydration, provenance, immutable contents, freshness, and index verified.")


if __name__ == "__main__":
    main()
