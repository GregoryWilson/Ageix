import json

from models.dependency_intelligence import DependencyClassification, DependencyValidationOutcome
from models.proposal_quality_models import ProposalQualityFailureCode
from services.dependency_intelligence_service import DependencyIntelligenceService
from services.proposal_quality_service import ProposalQualityService


def _write_controls(tmp_path, **overrides):
    path = tmp_path / ".ageix" / "config"
    path.mkdir(parents=True, exist_ok=True)
    config = {
        "dependency_intelligence": {
            "enabled": True,
            "max_depth": 2,
            "max_nodes": 50,
            "max_imports_per_file": 25,
            "follow_test_imports": True,
            "follow_runtime_imports": True,
            "allow_proposed_local_imports": True,
            "allow_existing_local_imports": True,
            "allow_stdlib_imports": True,
            "allowed_test_dependencies": ["pytest"],
            "blocked_dependencies": [],
            "unknown_dependency_policy": "fail",
        }
    }
    config["dependency_intelligence"].update(overrides)
    (path / "controls.json").write_text(json.dumps(config), encoding="utf-8")


def _proposal(path, content):
    return {"changes": [{"operation": "create_file", "path": path, "content": content}]}


def _classifications(result):
    return [item.classification for item in result.evidence]


def test_stdlib_dependency_classified(tmp_path):
    result = DependencyIntelligenceService(tmp_path).analyze(proposal=_proposal("services/example.py", "import json\n"))
    assert DependencyClassification.STDLIB_DEPENDENCY in _classifications(result)


def test_existing_repo_dependency_classified(tmp_path):
    (tmp_path / "utils").mkdir()
    (tmp_path / "utils" / "confidence_formatter.py").write_text("class ConfidenceFormatter:\n    marker = True\n")
    result = DependencyIntelligenceService(tmp_path).analyze(
        proposal=_proposal("services/example.py", "from utils.confidence_formatter import ConfidenceFormatter\n")
    )
    assert result.evidence[0].classification == DependencyClassification.EXISTING_REPO_DEPENDENCY
    assert result.evidence[0].resolved_path == "utils/confidence_formatter.py"


def test_proposed_repo_dependency_classified(tmp_path):
    proposal = {"changes": [
        {"operation": "create_file", "path": "services/example.py", "content": "from utils.confidence_formatter import ConfidenceFormatter\n"},
        {"operation": "create_file", "path": "utils/confidence_formatter.py", "content": "class ConfidenceFormatter:\n    marker = True\n"},
    ]}
    result = DependencyIntelligenceService(tmp_path).analyze(proposal=proposal)
    assert result.evidence[0].classification == DependencyClassification.PROPOSED_REPO_DEPENDENCY
    assert result.evidence[0].resolved_path == "utils/confidence_formatter.py"


def test_unknown_dependency_classified(tmp_path):
    result = DependencyIntelligenceService(tmp_path).analyze(proposal=_proposal("services/example.py", "import mystery_sdk\n"))
    assert result.evidence[0].classification == DependencyClassification.UNKNOWN_EXTERNAL_DEPENDENCY
    assert not result.passed


def test_recursive_dependency_discovery(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "b.py").write_text("import json\n")
    result = DependencyIntelligenceService(tmp_path).analyze(proposal=_proposal("services/a.py", "from pkg.b import value\n"))
    assert [e.dependency for e in result.evidence] == ["pkg.b", "json"]


def test_depth_limit_enforced(tmp_path):
    _write_controls(tmp_path, max_depth=0)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "b.py").write_text("import json\n")
    result = DependencyIntelligenceService(tmp_path).analyze(proposal=_proposal("services/a.py", "from pkg.b import value\n"))
    assert result.outcome == DependencyValidationOutcome.DEPTH_LIMIT_EXCEEDED


def test_node_limit_enforced(tmp_path):
    _write_controls(tmp_path, max_nodes=1)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "b.py").write_text("import json\n")
    result = DependencyIntelligenceService(tmp_path).analyze(proposal=_proposal("services/a.py", "from pkg.b import value\n"))
    assert result.outcome == DependencyValidationOutcome.NODE_LIMIT_EXCEEDED


def test_import_limit_enforced(tmp_path):
    _write_controls(tmp_path, max_imports_per_file=1)
    result = DependencyIntelligenceService(tmp_path).analyze(proposal=_proposal("services/a.py", "import json\nimport pathlib\n"))
    assert result.outcome == DependencyValidationOutcome.IMPORT_LIMIT_EXCEEDED


def test_controls_override_max_depth(tmp_path):
    _write_controls(tmp_path, max_depth=3)
    assert DependencyIntelligenceService(tmp_path).controls.max_depth == 3


def test_controls_override_max_nodes(tmp_path):
    _write_controls(tmp_path, max_nodes=7)
    assert DependencyIntelligenceService(tmp_path).controls.max_nodes == 7


def test_controls_override_import_limit(tmp_path):
    _write_controls(tmp_path, max_imports_per_file=4)
    assert DependencyIntelligenceService(tmp_path).controls.max_imports_per_file == 4


def test_pytest_classified_as_test_dependency(tmp_path):
    result = DependencyIntelligenceService(tmp_path).analyze(proposal=_proposal("tests/test_example.py", "import pytest\ndef test_x():\n    assert True\n"))
    assert result.evidence[0].classification == DependencyClassification.APPROVED_TEST_DEPENDENCY


def test_proposed_file_import_allowed(tmp_path):
    proposal = {"changes": [
        {"operation": "create_file", "path": "services/example.py", "content": "from utils.confidence_formatter import ConfidenceFormatter\n"},
        {"operation": "create_file", "path": "utils/confidence_formatter.py", "content": "class ConfidenceFormatter:\n    marker = True\n"},
    ]}
    result = ProposalQualityService(tmp_path).validate(proposal=proposal, objective="Create formatter", target_files=["services/example.py", "utils/confidence_formatter.py"])
    assert result.passed


def test_unknown_external_dependency_fails(tmp_path):
    result = ProposalQualityService(tmp_path).validate(proposal=_proposal("services/example.py", "import mystery_sdk\n"), objective="Create service", target_files=["services/example.py"])
    assert not result.passed
    assert result.violations[0].code == ProposalQualityFailureCode.UNSUPPORTED_DEPENDENCY_REFERENCE


def test_dependency_validation_evidence_created(tmp_path):
    result = DependencyIntelligenceService(tmp_path).analyze(proposal=_proposal("services/example.py", "import json\n"))
    assert result.evidence
    assert result.evidence[0].source_file == "services/example.py"


def test_dependency_resolution_path_recorded(tmp_path):
    (tmp_path / "utils").mkdir()
    (tmp_path / "utils" / "confidence_formatter.py").write_text("class ConfidenceFormatter:\n    marker = True\n")
    result = DependencyIntelligenceService(tmp_path).analyze(proposal=_proposal("services/example.py", "from utils.confidence_formatter import ConfidenceFormatter\n"))
    assert result.evidence[0].resolved_path == "utils/confidence_formatter.py"


def test_confidence_formatter_dependency_validation(tmp_path):
    proposal = {"changes": [
        {"operation": "create_file", "path": "services/example.py", "content": "from utils.confidence_formatter import ConfidenceFormatter\n"},
        {"operation": "create_file", "path": "utils/confidence_formatter.py", "content": "class ConfidenceFormatter:\n    marker = True\n"},
        {"operation": "create_file", "path": "tests/test_example.py", "content": "import pytest\nfrom utils.confidence_formatter import ConfidenceFormatter\ndef test_formatter():\n    assert ConfidenceFormatter\n"},
    ]}
    result = ProposalQualityService(tmp_path).validate(
        proposal=proposal,
        objective="Add confidence formatter",
        target_files=["services/example.py", "utils/confidence_formatter.py", "tests/test_example.py"],
    )
    assert result.passed
    assert any(e.classification == DependencyClassification.PROPOSED_REPO_DEPENDENCY for e in result.dependency_evidence)
    assert any(e.classification == DependencyClassification.APPROVED_TEST_DEPENDENCY for e in result.dependency_evidence)


def test_dependency_graph_generated_for_patch_proposal(tmp_path):
    result = DependencyIntelligenceService(tmp_path).analyze(proposal=_proposal("services/example.py", "import json\n"))
    assert result.graph
    assert result.graph[0].source_file == "services/example.py"


def test_dependency_intelligence_integrated_with_quality_validation(tmp_path):
    result = ProposalQualityService(tmp_path).validate(proposal=_proposal("services/example.py", "import json\n"), objective="Create service", target_files=["services/example.py"])
    assert result.passed
    assert result.dependency_evidence[0].classification == DependencyClassification.STDLIB_DEPENDENCY
