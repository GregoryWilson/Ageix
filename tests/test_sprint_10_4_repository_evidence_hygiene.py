from pathlib import Path

from agents import repository_agent
from services.planner_work_packet_service import PlannerWorkPacketService
from services.repository_evidence_service import RepositoryEvidenceService


def write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_repository_evidence_service_excludes_runtime_artifacts(tmp_path):
    write(tmp_path / "services" / "order_service.py", "class OrderService: pass")
    write(tmp_path / "tests" / "test_order_service.py", "def test_order(): pass")
    write(tmp_path / ".ageix" / "config" / "controls.json", "{}")
    write(tmp_path / ".ageix" / "manifests" / "patch.json", "{}")
    write(tmp_path / ".ageix" / "runs" / "Example" / "objective.json", "{}")
    write(tmp_path / ".ageix" / "verification" / "workspace" / "services" / "old.py", "")
    write(tmp_path / "artifacts" / "artifact.json", "{}")
    write(tmp_path / ".pytest_cache" / "v" / "cache", "")

    files = RepositoryEvidenceService(tmp_path).list_source_files()

    assert "services/order_service.py" in files
    assert "tests/test_order_service.py" in files
    assert ".ageix/config/controls.json" in files
    assert not any(path.startswith(".ageix/manifests/") for path in files)
    assert not any(path.startswith(".ageix/runs/") for path in files)
    assert not any(path.startswith(".ageix/verification/") for path in files)
    assert not any(path.startswith("artifacts/") for path in files)
    assert not any(".pytest_cache" in path for path in files)


def test_repository_agent_returns_compact_selected_files(tmp_path, monkeypatch):
    for index in range(30):
        write(tmp_path / "docs" / f"note_{index}.md", "noise")
    write(tmp_path / "services" / "example_service.py", "class ExampleService: pass")
    write(tmp_path / "tests" / "test_example_service.py", "def test_example(): pass")
    write(tmp_path / ".ageix" / "staged" / "patch" / "files" / "services" / "old_service.py", "")

    monkeypatch.setattr(repository_agent, "REPO_ROOT", tmp_path.resolve())

    result = repository_agent.run(
        {
            "objective": "Create an invoice service",
            "target_files": ["services/invoice_service.py", "tests/test_invoice_service.py"],
            "requested_operation": "create_file",
            "constraints": {"evidence_file_limit": 4, "allow_create_files": True},
        }
    )

    assert result["file_count"] == 32
    assert result["selected_file_count"] <= 4
    assert "services/example_service.py" in result["selected_files"]
    assert "tests/test_example_service.py" in result["selected_files"]
    assert not any(path.startswith(".ageix/staged/") for path in result["files"])


def test_planner_repository_examples_ignore_runtime_artifacts():
    packet = PlannerWorkPacketService().build(
        objective="Create a new local utility service for confidence formatting.",
        known_files=[
            ".ageix/staged/patch/files/services/old_service.py",
            ".ageix/verification/workspace/tests/test_old_service.py",
            "services/project_profile_service.py",
            "services/project_registry_service.py",
            "tests/test_project_profile_service.py",
            "tests/test_project_registry_service.py",
            "models/project_profile.py",
        ],
    )

    assert packet.repository_evidence
    assert "services/project_profile_service.py" in packet.repository_evidence
    assert any(path.startswith("tests/test_project") for path in packet.repository_evidence)
    assert not any(path.startswith(".ageix/") for path in packet.repository_evidence)


def test_repository_evidence_scoring_prefers_matching_patterns(tmp_path):
    files = [
        "docs/readme.md",
        "services/project_profile_service.py",
        "services/confidence_scoring_service.py",
        "tests/test_confidence_scoring_service.py",
        "models/validation_evidence.py",
    ]

    selected = RepositoryEvidenceService(tmp_path).select_evidence_files(
        objective="Create confidence formatting service",
        target_files=["services/confidence_formatter_service.py", "tests/test_confidence_formatter_service.py"],
        known_files=files,
        limit=3,
    )

    assert "services/confidence_scoring_service.py" in selected
    assert "tests/test_confidence_scoring_service.py" in selected
    assert "docs/readme.md" not in selected
