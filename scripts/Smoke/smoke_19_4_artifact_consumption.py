from __future__ import annotations

import pprint
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from models.capability_request import CapabilityRequest
from services.artifact_delivery_service import ArtifactDeliveryService
from services.capability_execution_service import CapabilityExecutionService
from services.repository_visibility_service import RepositoryVisibilityService


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def make_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    (repo / "services").mkdir()
    (repo / "services" / "alpha.py").write_text("print('alpha')\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial commit")
    return repo


def main() -> None:
    print("== Smoke 19.4: requesting-agent artifact consumption foundation ==")
    with TemporaryDirectory() as tmp:
        repo = make_repo(Path(tmp))
        archive = RepositoryVisibilityService(repo).create_archive(paths=["services"], archive_name="services_only.zip")
        execution = CapabilityExecutionService(repo)
        pushed = execution.execute(CapabilityRequest(
            capability_id="artifact.push",
            session_id="S19_4",
            agent_id="lex",
            arguments={
                "artifact_id": archive["artifact_id"],
                "client_id": "chatGPT",
                "provider": "OpenAI",
                "client_context": {"client_id": "chatGPT", "provider": "OpenAI", "agent_id": "lex"},
            },
        ))
        fetched = execution.execute(CapabilityRequest(
            capability_id="artifact.delivery.get",
            session_id="S19_4",
            agent_id="lex",
            arguments={"delivery_id": pushed.result["delivery_id"]},
        ))
        local_export = ArtifactDeliveryService(repo).push(artifact_id=archive["artifact_id"], destination="local_export")
        summary = {
            "artifact_id": archive["artifact_id"],
            "requesting_agent_delivery_id": pushed.result["delivery_id"],
            "destination": pushed.result["destination"],
            "agent_id": pushed.result.get("agent_id"),
            "client_id": pushed.result.get("client_id"),
            "provider": pushed.result.get("provider"),
            "consumption_ready": pushed.result.get("consumption_ready"),
            "raw_reference_hidden": "delivery_reference" not in pushed.result,
            "has_delivery_reference": pushed.result.get("has_delivery_reference"),
            "fetched_destination": fetched.result["destination"],
            "fetched_transport": fetched.result["metadata"].get("transport"),
            "local_export_still_supported": local_export["destination"] == "local_export" and local_export["has_delivery_reference"] is True,
        }
        pprint.pprint(summary)
        assert pushed.success is True
        assert fetched.success is True
        assert summary["destination"] == "requesting_agent"
        assert summary["agent_id"] == "lex"
        assert summary["client_id"] == "chatGPT"
        assert summary["provider"] == "OpenAI"
        assert summary["consumption_ready"] is True
        assert summary["raw_reference_hidden"] is True
        assert summary["has_delivery_reference"] is False
        assert summary["fetched_transport"] == "mcp_governed_artifact_reference"
        assert summary["local_export_still_supported"] is True
    print("Smoke 19.4 PASS: requesting-agent artifact push, identity-derived delivery metadata, summary-first consumption record, and local export compatibility validated.")


if __name__ == "__main__":
    main()
