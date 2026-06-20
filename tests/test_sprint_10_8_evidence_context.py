import json

from chair import validate_patch_proposal_deliverable
from models.work_packet import WorkPacket
from services.code_context_extractor import CodeContextExtractor
from services.evidence_context_service import EvidenceContextService
from services.patch_proposal_contract_service import PatchProposalContractService
from services.planner_work_packet_service import PlannerWorkPacketService


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _controls(tmp_path, **overrides):
    config = {"evidence_context": overrides}
    path = tmp_path / ".ageix" / "config"
    path.mkdir(parents=True, exist_ok=True)
    (path / "controls.json").write_text(json.dumps(config), encoding="utf-8")


def _proposal(path="services/example.py"):
    return {
        "result_type": "patch_proposal",
        "objective": "Change example",
        "summary": "Change example",
        "files_considered": [path],
        "evidence_used": [],
        "dependency_hints_used": [],
        "assumptions": [],
        "dependency_risks": [],
        "changes": [{"path": path, "operation": "replace_file", "content": "class Example:\n    pass\n"}],
        "test_plan": ["PYTHONPATH=. python -m pytest"],
        "no_write_confirmation": True,
    }


def _sample_repo(tmp_path):
    _write(
        tmp_path / "services" / "example.py",
        "import os\nfrom pathlib import Path\n\nVALUE = 1\n\ndef _helper():\n    return VALUE\n\ndef target_function():\n    return _helper()\n\nclass Example:\n    def run(self):\n        return target_function()\n",
    )
    _write(
        tmp_path / "tests" / "test_example.py",
        "from services.example import target_function\n\ndef test_target_function():\n    assert target_function() == 1\n",
    )
    _write(tmp_path / "services" / "unrelated.py", "class Unrelated:\n    pass\n")


def test_planner_context_contains_summaries(tmp_path):
    _sample_repo(tmp_path)
    packet = PlannerWorkPacketService(tmp_path).build(
        objective="Change example service",
        task={"target_files": ["services/example.py"]},
    )

    context = EvidenceContextService(tmp_path).build_planner_context(packet)

    assert context.worker == "planner"
    assert context.repository_summaries
    assert context.selection_evidence.worker == "planner"
    assert not context.raw_graphs_included


def test_devworker_context_contains_code_slices(tmp_path):
    _sample_repo(tmp_path)
    packet = PlannerWorkPacketService(tmp_path).build(
        objective="Change example service",
        task={"target_files": ["services/example.py"]},
    )

    context = EvidenceContextService(tmp_path).build_devworker_context(packet)

    assert "services/example.py" in context.files
    assert "import os" in context.files["services/example.py"]
    assert "target_function" in context.files["services/example.py"]
    assert "services/unrelated.py" not in context.files


def test_validation_context_contains_full_evidence(tmp_path):
    _sample_repo(tmp_path)
    packet = PlannerWorkPacketService(tmp_path).build(
        objective="Change example service",
        task={"target_files": ["services/example.py"]},
    )

    context = EvidenceContextService(tmp_path).build_validation_context(
        packet,
        runtime_evidence={"pytest": "passed"},
    )

    assert context.worker == "validation"
    assert context.full_repository_inventory_included is True
    assert "runtime evidence keys" in context.summary
    assert context.impact_summary


def test_cloud_context_excludes_raw_graphs(tmp_path):
    _sample_repo(tmp_path)
    packet = PlannerWorkPacketService(tmp_path).build(
        objective="Change example service",
        task={"target_files": ["services/example.py"]},
    )

    context = EvidenceContextService(tmp_path).build_cloud_context(
        packet,
        impact_evidence={"impact_graph": {"a": ["b"]}, "status": "pass"},
        dependency_evidence={"graph": {"a": ["b"]}, "status": "pass"},
    )

    assert context.raw_graphs_included is False
    assert context.full_repository_inventory_included is False
    assert "impact_graph" not in context.impact_summary
    assert "graph" not in context.dependency_summary


def test_extract_function_slice(tmp_path):
    _sample_repo(tmp_path)
    result = CodeContextExtractor(tmp_path).extract_function_slice("services/example.py", "target_function")
    assert "def target_function" in result
    assert "import os" in result


def test_extract_class_slice(tmp_path):
    _sample_repo(tmp_path)
    result = CodeContextExtractor(tmp_path).extract_class_slice("services/example.py", "Example")
    assert "class Example" in result
    assert "def run" in result


def test_extract_imports(tmp_path):
    _sample_repo(tmp_path)
    result = CodeContextExtractor(tmp_path).extract_imports("services/example.py")
    assert "import os" in result
    assert "from pathlib import Path" in result
    assert "class Example" not in result


def test_extract_adjacent_helpers(tmp_path):
    _sample_repo(tmp_path)
    result = CodeContextExtractor(tmp_path).extract_function_slice("services/example.py", "target_function")
    assert "def _helper" in result


def test_full_file_fallback(tmp_path):
    _write(tmp_path / "services" / "broken.py", "def broken(:\n    pass\n")
    result = CodeContextExtractor(tmp_path).extract_file_slice("services/broken.py", max_lines=1)
    assert result == "def broken(:\n"


def test_devworker_cannot_expand_scope():
    request = PatchProposalContractService().architecture_scope_exceeded_request(
        requested_files=["services/new_architecture.py", "tests/test_new_architecture.py"]
    )
    assert request["result_type"] == "context_request"
    assert request["reason"] == "architecture_scope_exceeded"
    assert request["recommended_planner_revisit"] is True


def test_scope_validation_rejects_unapproved_file():
    proposal = _proposal("services/unapproved.py")
    try:
        validate_patch_proposal_deliverable(proposal, approved_scope=["services/example.py"])
    except ValueError as ex:
        assert "scope_validation_failed" in str(ex)
    else:
        raise AssertionError("Expected unapproved scope to fail")


def test_architecture_scope_exceeded_request():
    request = {
        "result_type": "context_request",
        "reason": "architecture_scope_exceeded",
        "requested_files": ["services/new_scope.py"],
        "recommended_planner_revisit": True,
    }
    validate_patch_proposal_deliverable(request)


def test_max_files_enforced(tmp_path):
    _sample_repo(tmp_path)
    _controls(tmp_path, max_files=1)
    packet = WorkPacket(
        objective="Budget files",
        target_files=["services/example.py", "tests/test_example.py", "services/unrelated.py"],
        approved_scope=["services/example.py", "tests/test_example.py", "services/unrelated.py"],
    )

    context = EvidenceContextService(tmp_path).build_devworker_context(packet)

    assert len(context.selection_evidence.selected_files) == 1
    assert context.selection_evidence.excluded_files
    assert context.selection_evidence.budget_applied is True


def test_max_chars_enforced(tmp_path):
    _write(tmp_path / "services" / "large.py", "\n".join(f"line_{i} = {i}" for i in range(200)))
    _controls(tmp_path, max_chars=80, max_slice_lines_per_file=120)
    packet = WorkPacket(
        objective="Budget chars",
        target_files=["services/large.py"],
        approved_scope=["services/large.py"],
    )

    context = EvidenceContextService(tmp_path).build_devworker_context(packet)

    assert context.selection_evidence.selected_chars <= 80
    assert context.selection_evidence.budget_applied is True


def test_overflow_summarization(tmp_path):
    _write(tmp_path / "services" / "large.py", "\n".join(f"line_{i} = {i}" for i in range(200)))
    _controls(tmp_path, max_chars=120, overflow_policy="summarize")
    packet = WorkPacket(
        objective="Overflow summary",
        target_files=["services/large.py"],
        approved_scope=["services/large.py"],
    )

    context = EvidenceContextService(tmp_path).build_devworker_context(packet)

    assert "services/large.py" in context.files
    assert "lines" in context.files["services/large.py"]


def test_target_scoped_context_smaller_than_repo_context(tmp_path):
    _sample_repo(tmp_path)
    for index in range(10):
        _write(tmp_path / "services" / f"extra_{index}.py", "x = '" + ("a" * 1000) + "'\n")
    packet = WorkPacket(
        objective="Scoped context",
        target_files=["services/example.py"],
        approved_scope=["services/example.py"],
    )

    context = EvidenceContextService(tmp_path).build_devworker_context(packet)
    repo_chars = sum(len(path.read_text(encoding="utf-8")) for path in (tmp_path / "services").glob("*.py"))

    assert context.selection_evidence.selected_chars < repo_chars


def test_devworker_receives_only_relevant_files(tmp_path):
    _sample_repo(tmp_path)
    packet = WorkPacket(
        objective="Scoped implementation",
        target_files=["services/example.py", "services/unrelated.py"],
        approved_scope=["services/example.py"],
    )

    context = EvidenceContextService(tmp_path).build_devworker_context(packet)

    assert list(context.files) == ["services/example.py"]


def test_scope_escalation_routes_to_planner():
    request = PatchProposalContractService().architecture_scope_exceeded_request(
        requested_files=["services/a.py"]
    )
    assert request["recommended_planner_revisit"] is True


def test_chair_governance_blocks_scope_expansion():
    try:
        validate_patch_proposal_deliverable(_proposal("services/out_of_scope.py"), approved_scope=["services/example.py"])
    except ValueError as ex:
        assert "proposal_targets must be within approved_scope" in str(ex)
    else:
        raise AssertionError("Expected Chair governance to block scope expansion")


def test_evidence_selection_is_deterministic(tmp_path):
    _sample_repo(tmp_path)
    packet = WorkPacket(
        objective="Determinism",
        target_files=["services/example.py", "tests/test_example.py"],
        approved_scope=["services/example.py", "tests/test_example.py"],
    )
    service = EvidenceContextService(tmp_path)

    first = service.build_devworker_context(packet).selection_evidence
    second = service.build_devworker_context(packet).selection_evidence

    assert first.selected_files == second.selected_files
    assert first.selected_chars == second.selected_chars
    assert first.selection_reason == second.selection_reason
