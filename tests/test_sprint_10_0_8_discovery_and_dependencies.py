from pathlib import Path

from agents import repository_agent
from chair import build_devworker_packet, filter_context_requested_files
from models.proposal_quality_models import ProposalQualityFailureCode
from services.proposal_quality_service import ProposalQualityService


def test_create_file_missing_target_is_valid_repository_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(repository_agent, "REPO_ROOT", tmp_path.resolve())

    result = repository_agent.run(
        {
            "target_files": ["agents/3D_printer_agent.py"],
            "requested_operation": "create_file",
        }
    )

    evidence = result["evidence"][0]
    assert evidence["path"] == "agents/3D_printer_agent.py"
    assert evidence["target_file_missing"] is True
    assert evidence["file_missing_create_allowed"] is True
    assert evidence["repository_evidence_status"] == "missing_allowed_for_create"


def test_replace_file_missing_target_remains_violation(tmp_path, monkeypatch):
    monkeypatch.setattr(repository_agent, "REPO_ROOT", tmp_path.resolve())

    result = repository_agent.run(
        {
            "target_files": ["agents/3D_printer_agent.py"],
            "requested_operation": "replace_file",
        }
    )

    evidence = result["evidence"][0]
    assert evidence["target_file_missing"] is True
    assert evidence["file_missing_create_allowed"] is False
    assert evidence["repository_evidence_status"] == "missing_violation"


def test_create_file_does_not_request_missing_target_again():
    requested = [{"path": "agents/3D_printer_agent.py"}]
    evidence = [
        {
            "path": "agents/3D_printer_agent.py",
            "repository_evidence_status": "missing_allowed_for_create",
            "file_missing_create_allowed": True,
        }
    ]

    files = filter_context_requested_files(
        requested,
        evidence,
        {"allow_create_files": True, "allowed_operations": ["replace_file", "create_file"]},
    )

    assert files == []


def test_create_file_preserves_requested_target_path():
    repository_result = {
        "evidence": [
            {
                "path": "agents/3D_printer_agent.py",
                "repository_evidence_status": "missing_allowed_for_create",
                "file_missing_create_allowed": True,
            }
        ],
        "requested_operation": "create_file",
        "dependency_hints": [],
    }

    packet = build_devworker_packet(
        objective="Create a 3D printer agent",
        target_files=["agents/3D_printer_agent.py"],
        repository_result=repository_result,
        step_constraints={"allow_create_files": True},
    )

    assert packet["target_files"] == ["agents/3D_printer_agent.py"]
    assert packet["repository_discovery"]["missing_allowed_for_create"] == [
        "agents/3D_printer_agent.py"
    ]


def _proposal_with_content(content: str) -> dict:
    return {
        "changes": [
            {
                "operation": "create_file",
                "path": "services/example_service.py",
                "content": content,
            }
        ]
    }


def test_dependency_validation_allows_stdlib_import(tmp_path):
    result = ProposalQualityService(tmp_path).validate(
        proposal=_proposal_with_content("import json\nfrom pathlib import Path\n"),
        objective="Create service",
        target_files=["services/example_service.py"],
    )

    assert result.passed


def test_dependency_validation_allows_repository_import(tmp_path):
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "__init__.py").write_text("")

    result = ProposalQualityService(tmp_path).validate(
        proposal=_proposal_with_content("from services.controls_service import ControlsService\n"),
        objective="Create service",
        target_files=["services/example_service.py"],
    )

    assert result.passed


def test_dependency_validation_rejects_unknown_third_party_import(tmp_path):
    result = ProposalQualityService(tmp_path).validate(
        proposal=_proposal_with_content("from dependency_injection import inject\n"),
        objective="Create service",
        target_files=["services/example_service.py"],
    )

    assert not result.passed
    assert result.violations[0].code == ProposalQualityFailureCode.UNSUPPORTED_DEPENDENCY_REFERENCE


def test_dependency_validation_reads_requirements_txt(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests>=2\n")

    result = ProposalQualityService(tmp_path).validate(
        proposal=_proposal_with_content("import requests\n"),
        objective="Create service",
        target_files=["services/example_service.py"],
    )

    assert result.passed


def test_dependency_validation_reads_pyproject_toml(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["octoprint-client>=1.0"]\n'
    )

    result = ProposalQualityService(tmp_path).validate(
        proposal=_proposal_with_content("import octoprint_client\n"),
        objective="Create service",
        target_files=["services/example_service.py"],
    )

    assert result.passed


def test_external_api_usage_marks_research_required(tmp_path):
    result = ProposalQualityService(tmp_path).validate(
        proposal=_proposal_with_content("class OctoPrintAgent:\n    def status(self):\n        return \"unknown\"\n"),
        objective="Create a worker using the OctoPrint API library",
        target_files=["services/example_service.py"],
    )

    assert result.passed
    assert result.research_required is True
    assert result.escalation_recommended is True
    assert result.escalation["target"] == "research"
