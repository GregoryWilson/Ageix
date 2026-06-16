import json

from services.planner_work_packet_service import PlannerWorkPacketService
from services.proposal_quality_service import ProposalQualityService
from services.repository_impact_service import RepositoryImpactService


def _write_controls(tmp_path, **overrides):
    path = tmp_path / ".ageix" / "config"
    path.mkdir(parents=True, exist_ok=True)
    config = {
        "dependency_intelligence": {
            "enabled": True,
            "max_depth": 4,
            "max_nodes": 100,
            "max_imports_per_file": 25,
            "follow_test_imports": True,
            "follow_runtime_imports": True,
            "allow_proposed_local_imports": True,
            "allow_existing_local_imports": True,
            "allow_stdlib_imports": True,
            "allowed_test_dependencies": ["pytest"],
            "blocked_dependencies": [],
            "unknown_dependency_policy": "warn",
        },
        "repository_impact": {
            "enabled": True,
            "max_depth": 2,
            "max_nodes": 75,
            "max_dependents_per_file": 25,
            "include_tests": True,
            "include_runtime_files": True,
            "include_companion_tests": True,
            "impacted_test_depth": 1,
            "auto_add_companion_tests": True,
            "auto_add_impacted_tests": True,
            "recommend_indirect_dependents": True,
            "circular_dependency_policy": "warn_stop_path",
            "unresolved_import_policy": "warn",
            "unknown_impact_policy": "warn",
            "limit_policy": "warn",
        },
    }
    config["repository_impact"].update(overrides)
    (path / "controls.json").write_text(json.dumps(config), encoding="utf-8")


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_direct_dependent_detected(tmp_path):
    _write(tmp_path / "services" / "controls_service.py", "class ControlsService: pass\n")
    _write(tmp_path / "services" / "consumer.py", "from services.controls_service import ControlsService\n")

    result = RepositoryImpactService(tmp_path).analyze(target_files=["services/controls_service.py"])

    assert "services/consumer.py" in result.impacted_files
    assert any(e.relationship == "direct_dependent" for e in result.evidence)


def test_indirect_dependent_detected(tmp_path):
    _write(tmp_path / "services" / "base.py", "class Base: pass\n")
    _write(tmp_path / "services" / "middle.py", "from services.base import Base\n")
    _write(tmp_path / "services" / "top.py", "from services.middle import value\n")

    result = RepositoryImpactService(tmp_path).analyze(target_files=["services/base.py"])

    assert "services/top.py" in result.impacted_files
    assert any(e.impacted_file == "services/top.py" and e.relationship == "indirect_dependent" for e in result.evidence)


def test_companion_test_detected(tmp_path):
    _write(tmp_path / "services" / "controls_service.py", "class ControlsService: pass\n")

    result = RepositoryImpactService(tmp_path).analyze(target_files=["services/controls_service.py"])

    assert "tests/test_controls_service.py" in result.companion_files
    assert any(e.relationship == "companion_test" for e in result.evidence)


def test_impacted_test_detected(tmp_path):
    _write(tmp_path / "services" / "controls_service.py", "class ControlsService: pass\n")
    _write(tmp_path / "tests" / "test_controls_service.py", "from services.controls_service import ControlsService\ndef test_service():\n    assert ControlsService\n")

    result = RepositoryImpactService(tmp_path).analyze(target_files=["services/controls_service.py"])

    assert "tests/test_controls_service.py" in result.impacted_tests
    assert any(e.relationship == "impacted_test" for e in result.evidence)


def test_unrelated_file_excluded(tmp_path):
    _write(tmp_path / "services" / "controls_service.py", "class ControlsService: pass\n")
    _write(tmp_path / "services" / "unrelated.py", "class Other: pass\n")

    result = RepositoryImpactService(tmp_path).analyze(target_files=["services/controls_service.py"])

    assert "services/unrelated.py" not in result.impacted_files


def test_impact_max_depth_enforced(tmp_path):
    _write_controls(tmp_path, max_depth=1)
    _write(tmp_path / "services" / "a.py", "class A: pass\n")
    _write(tmp_path / "services" / "b.py", "from services.a import A\n")
    _write(tmp_path / "services" / "c.py", "from services.b import B\n")

    result = RepositoryImpactService(tmp_path).analyze(target_files=["services/a.py"])

    assert "impact_depth_limit_exceeded" in result.violations


def test_impact_max_nodes_enforced(tmp_path):
    _write_controls(tmp_path, max_nodes=1)
    _write(tmp_path / "services" / "a.py", "class A: pass\n")
    for index in range(3):
        _write(tmp_path / "services" / f"b{index}.py", "from services.a import A\n")

    result = RepositoryImpactService(tmp_path).analyze(target_files=["services/a.py"])

    assert "impact_node_limit_exceeded" in result.violations


def test_impact_dependents_limit_enforced(tmp_path):
    _write_controls(tmp_path, max_dependents_per_file=1)
    _write(tmp_path / "services" / "a.py", "class A: pass\n")
    for index in range(3):
        _write(tmp_path / "services" / f"b{index}.py", "from services.a import A\n")

    result = RepositoryImpactService(tmp_path).analyze(target_files=["services/a.py"])

    assert "impact_dependents_limit_exceeded" in result.violations


def test_impact_controls_disable_service(tmp_path):
    _write_controls(tmp_path, enabled=False)
    result = RepositoryImpactService(tmp_path).analyze(target_files=["services/a.py"])
    assert result.status == "disabled"




def test_repository_impact_excludes_virtualenv_paths(tmp_path):
    _write(tmp_path / "services" / "controls_service.py", "class ControlsService: pass\n")
    _write(
        tmp_path / "venv" / "lib" / "python3.14" / "site-packages" / "yaml" / "cyaml.py",
        "from yaml._yaml import CParser\n",
    )

    result = RepositoryImpactService(tmp_path).analyze(target_files=["services/controls_service.py"])

    assert not any("venv/" in item for item in result.impacted_files)
    assert not any("site-packages" in warning for warning in result.violations)


def test_repository_impact_exclude_paths_control_is_configurable(tmp_path):
    _write_controls(tmp_path, exclude_paths=["generated/"])
    _write(tmp_path / "services" / "a.py", "class A: pass\n")
    _write(tmp_path / "generated" / "consumer.py", "from services.a import A\n")

    result = RepositoryImpactService(tmp_path).analyze(target_files=["services/a.py"])

    assert "generated/consumer.py" not in result.impacted_files

def test_circular_dependency_warns_and_stops_path(tmp_path):
    _write(tmp_path / "services" / "a.py", "from services.b import B\n")
    _write(tmp_path / "services" / "b.py", "from services.a import A\n")

    result = RepositoryImpactService(tmp_path).analyze(target_files=["services/a.py"])

    assert "circular_dependency_detected" in result.violations


def test_planner_work_packet_includes_impacted_tests(tmp_path):
    _write(tmp_path / "services" / "controls_service.py", "class ControlsService: pass\n")
    _write(tmp_path / "tests" / "test_controls_service.py", "from services.controls_service import ControlsService\ndef test_service():\n    assert ControlsService\n")

    packet = PlannerWorkPacketService(tmp_path).build(
        objective="Change controls service",
        task={"target_files": ["services/controls_service.py"]},
    )

    assert "tests/test_controls_service.py" in packet.impacted_tests
    assert "tests/test_controls_service.py" in packet.test_targets


def test_planner_adds_companion_test_target(tmp_path):
    _write(tmp_path / "services" / "promotion_service.py", "class PromotionService: pass\n")

    packet = PlannerWorkPacketService(tmp_path).build(
        objective="Change promotion service",
        task={"target_files": ["services/promotion_service.py"]},
    )

    assert "tests/test_promotion_service.py" in packet.target_files
    assert "tests/test_promotion_service.py" in packet.companion_files


def test_planner_impact_summary_created(tmp_path):
    _write(tmp_path / "services" / "controls_service.py", "class ControlsService: pass\n")

    packet = PlannerWorkPacketService(tmp_path).build(
        objective="Change controls service",
        task={"target_files": ["services/controls_service.py"]},
    )

    assert packet.impact_summary["status"] in {"pass", "warn"}
    assert "confidence" in packet.impact_summary


def test_validation_warns_when_impacted_test_missing(tmp_path):
    _write(tmp_path / "services" / "controls_service.py", "class ControlsService: pass\n")
    _write(tmp_path / "tests" / "test_controls_service.py", "from services.controls_service import ControlsService\ndef test_service():\n    assert ControlsService\n")
    proposal = {"changes": [{"operation": "replace_file", "path": "services/controls_service.py", "content": "class ControlsService:\n    marker = True\n"}]}

    result = ProposalQualityService(tmp_path).validate(
        proposal=proposal,
        objective="Change controls service",
        target_files=["services/controls_service.py", "tests/test_controls_service.py"],
    )

    assert any(warning.startswith("impacted_test_missing") for warning in result.impact_warnings)


def test_validation_passes_when_impacted_test_present(tmp_path):
    _write(tmp_path / "services" / "controls_service.py", "class ControlsService: pass\n")
    _write(tmp_path / "tests" / "test_controls_service.py", "from services.controls_service import ControlsService\ndef test_service():\n    assert ControlsService\n")
    proposal = {"changes": [
        {"operation": "replace_file", "path": "services/controls_service.py", "content": "class ControlsService:\n    marker = True\n"},
        {"operation": "replace_file", "path": "tests/test_controls_service.py", "content": "from services.controls_service import ControlsService\ndef test_service():\n    assert ControlsService.marker is True\n"},
    ]}

    result = ProposalQualityService(tmp_path).validate(
        proposal=proposal,
        objective="Change controls service",
        target_files=["services/controls_service.py", "tests/test_controls_service.py"],
    )

    assert result.passed
    assert not any(warning.startswith("impacted_test_missing") for warning in result.impact_warnings)


def test_validation_records_impact_evidence(tmp_path):
    _write(tmp_path / "services" / "controls_service.py", "class ControlsService: pass\n")
    proposal = {"changes": [{"operation": "replace_file", "path": "services/controls_service.py", "content": "class ControlsService:\n    marker = True\n"}]}

    result = ProposalQualityService(tmp_path).validate(
        proposal=proposal,
        objective="Change controls service",
        target_files=["services/controls_service.py"],
    )

    assert result.impact_evidence
    assert result.impact_summary


def test_controls_service_change_identifies_controls_tests():
    result = RepositoryImpactService(".").analyze(target_files=["services/controls_service.py"])
    assert "tests/test_controls_service.py" in result.impacted_tests


def test_promotion_service_change_identifies_promotion_tests():
    result = RepositoryImpactService(".").analyze(target_files=["services/promotion_service.py"])
    assert "tests/test_promotion_service.py" in result.impacted_tests


def test_chair_change_identifies_high_impact_dependencies():
    result = RepositoryImpactService(".").analyze(target_files=["chair.py"])
    assert result.summary["impacted_files_count"] >= 1
    assert result.summary["status"] in {"pass", "warn"}
