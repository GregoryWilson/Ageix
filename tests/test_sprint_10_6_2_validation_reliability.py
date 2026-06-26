from chair import normalize_patch_proposal_deliverable, validate_patch_proposal_deliverable
from models.proposal_quality_models import ProposalQualityFailureCode
from services.behavioral_smoke_verifier import BehavioralSmokeVerifier
from services.proposal_quality_service import ProposalQualityService
from services.requirement_trace_service import RequirementTraceService
from services.validation_evidence_service import ValidationEvidenceService


def _proposal(changes):
    return {
        "result_type": "patch_proposal",
        "objective": "Create utils/math_helpers.py with an add function and create pytest tests for it.",
        "summary": "Create math helper and tests",
        "changes": changes,
    }


def test_pytest_assert_recognized():
    result = ProposalQualityService(".").validate(
        proposal=_proposal([
            {
                "operation": "create_file",
                "path": "tests/test_math_helpers.py",
                "content": "def test_add():\n    assert 1 + 2 == 3\n",
            }
        ]),
        objective="Create meaningful pytest test",
        target_files=["tests/test_math_helpers.py"],
    )

    assert ProposalQualityFailureCode.TEST_WITHOUT_ASSERTION not in {v.code for v in result.violations}


def test_unittest_assert_equal_recognized():
    content = """import unittest

class TestFormatter(unittest.TestCase):
    def test_format_confidence(self):
        self.assertEqual('50.00%', '50.00%')
"""

    result = ProposalQualityService(".").validate(
        proposal=_proposal([
            {
                "operation": "create_file",
                "path": "tests/test_formatter.py",
                "content": content,
            }
        ]),
        objective="Create meaningful unittest test",
        target_files=["tests/test_formatter.py"],
    )

    assert ProposalQualityFailureCode.TEST_WITHOUT_ASSERTION not in {v.code for v in result.violations}


def test_unittest_assert_true_recognized():
    content = """import unittest

class TestFormatter(unittest.TestCase):
    def test_format_confidence(self):
        self.assertTrue('50.00%'.endswith('%'))
"""

    result = ProposalQualityService(".").validate(
        proposal=_proposal([
            {
                "operation": "create_file",
                "path": "tests/test_formatter.py",
                "content": content,
            }
        ]),
        objective="Create meaningful unittest test",
        target_files=["tests/test_formatter.py"],
    )

    assert ProposalQualityFailureCode.TEST_WITHOUT_ASSERTION not in {v.code for v in result.violations}


def test_unittest_assert_raises_recognized():
    content = """import unittest

class TestFormatter(unittest.TestCase):
    def test_format_confidence(self):
        with self.assertRaises(ValueError):
            raise ValueError('bad')
"""

    result = ProposalQualityService(".").validate(
        proposal=_proposal([
            {
                "operation": "create_file",
                "path": "tests/test_formatter.py",
                "content": content,
            }
        ]),
        objective="Create meaningful unittest test",
        target_files=["tests/test_formatter.py"],
    )

    assert ProposalQualityFailureCode.TEST_WITHOUT_ASSERTION not in {v.code for v in result.violations}


def test_create_file_generates_implementation_evidence():
    proposal = _proposal([
        {
            "operation": "create_file",
            "path": "utils/math_helpers.py",
            "content": "def add(a, b):\n    return a + b\n",
        }
    ])

    result = RequirementTraceService().validate(
        proposal=proposal,
        success_criteria=["Authorized target file exists in proposal: utils/math_helpers.py"],
        require_test_evidence=True,
    )

    assert result.passed
    assert result.traces[0].implementation_evidence[0].file_path == "utils/math_helpers.py"


def test_create_file_generates_test_evidence():
    proposal = _proposal([
        {
            "operation": "create_file",
            "path": "tests/test_math_helpers.py",
            "content": "def test_add():\n    assert 1 + 2 == 3\n",
        }
    ])

    result = RequirementTraceService().validate(
        proposal=proposal,
        success_criteria=["Executable test target exists: tests/test_math_helpers.py"],
        require_test_evidence=True,
    )

    assert result.passed
    assert result.traces[0].test_evidence[0].file_path == "tests/test_math_helpers.py"


def test_replace_file_generates_implementation_evidence():
    proposal = _proposal([
        {
            "operation": "replace_file",
            "path": "services/example_service.py",
            "content": "VALUE = 1\n",
        }
    ])

    result = RequirementTraceService().validate(
        proposal=proposal,
        success_criteria=["Authorized target file exists in proposal: services/example_service.py"],
        require_test_evidence=True,
    )

    assert result.passed
    assert result.traces[0].implementation_evidence[0].file_path == "services/example_service.py"


def test_new_test_file_maps_to_requirement():
    proposal = _proposal([
        {
            "operation": "create_file",
            "path": "tests/test_math_helpers.py",
            "content": "def test_add():\n    assert 1 + 2 == 3\n",
        }
    ])
    trace_result = RequirementTraceService().validate(
        proposal=proposal,
        success_criteria=["Executable test target exists: tests/test_math_helpers.py"],
    )

    result = ValidationEvidenceService().validate(
        proposal=proposal,
        trace_result=trace_result,
        behavior_result=BehavioralSmokeVerifier().verify(proposal=proposal, objective="", success_criteria=[]),
    )

    assert "UNMAPPED_TEST_EVIDENCE" not in {v.code for v in result.violations}


def test_multiple_test_files_map_to_requirements():
    proposal = _proposal([
        {"operation": "create_file", "path": "tests/test_one.py", "content": "def test_one():\n    assert 1\n"},
        {"operation": "create_file", "path": "tests/test_two.py", "content": "def test_two():\n    assert 2\n"},
    ])
    trace_result = RequirementTraceService().validate(
        proposal=proposal,
        success_criteria=[
            "Executable test target exists: tests/test_one.py",
            "Executable test target exists: tests/test_two.py",
        ],
    )

    result = ValidationEvidenceService().validate(
        proposal=proposal,
        trace_result=trace_result,
        behavior_result=BehavioralSmokeVerifier().verify(proposal=proposal, objective="", success_criteria=[]),
    )

    assert result.passed


def test_existing_test_file_maps_to_requirement():
    proposal = _proposal([
        {"operation": "replace_file", "path": "tests/test_existing.py", "content": "def test_existing():\n    assert True is True\n"},
    ])
    trace_result = RequirementTraceService().validate(
        proposal=proposal,
        success_criteria=["Executable test target exists: tests/test_existing.py"],
    )

    result = ValidationEvidenceService().validate(
        proposal=proposal,
        trace_result=trace_result,
        behavior_result=BehavioralSmokeVerifier().verify(proposal=proposal, objective="", success_criteria=[]),
    )

    assert result.passed


def test_missing_changes_field():
    proposal = {
        "result_type": "patch_proposal",
        "objective": "Create utility",
        "summary": "Create utility",
        "files_considered": [],
        "evidence_used": [],
        "dependency_hints_used": [],
        "assumptions": [],
        "dependency_risks": [],
        "test_plan": [],
        "no_write_confirmation": True,
    }

    try:
        validate_patch_proposal_deliverable(proposal)
    except ValueError as ex:
        assert "missing_changes_field" in str(ex)
    else:
        raise AssertionError("Expected missing changes field failure")


def test_empty_patch_proposal():
    proposal = normalize_patch_proposal_deliverable(
        {
            "result_type": "patch_proposal",
            "objective": "Create utility",
            "summary": "Create utility",
            "files_considered": [],
            "evidence_used": [],
            "dependency_hints_used": [],
            "assumptions": [],
            "dependency_risks": [],
            "proposed_changes": [],
            "test_plan": [],
            "no_write_confirmation": True,
        }
    )

    try:
        validate_patch_proposal_deliverable(proposal)
    except ValueError as ex:
        assert "empty_patch_proposal" in str(ex)
    else:
        raise AssertionError("Expected empty proposal failure")


def test_invalid_patch_operation():
    proposal = normalize_patch_proposal_deliverable(
        {
            "result_type": "patch_proposal",
            "objective": "Create utility",
            "summary": "Create utility",
            "files_considered": [],
            "evidence_used": [],
            "dependency_hints_used": [],
            "assumptions": [],
            "dependency_risks": [],
            "changes": [{"path": "utils/example.py", "operation": "delete_file", "content": ""}],
            "test_plan": [],
            "no_write_confirmation": True,
        }
    )

    try:
        validate_patch_proposal_deliverable(proposal)
    except ValueError as ex:
        assert "invalid_patch_operation" in str(ex)
    else:
        raise AssertionError("Expected invalid operation failure")


def test_validation_evidence_includes_stage_type_and_source_file():
    proposal = _proposal([
        {
            "operation": "create_file",
            "path": "tests/test_math_helpers.py",
            "content": "def test_add():\n    assert 1 + 2 == 3\n",
        }
    ])
    trace_result = RequirementTraceService().validate(
        proposal=proposal,
        success_criteria=["Executable test target exists: tests/test_math_helpers.py"],
    )

    result = ValidationEvidenceService().validate(
        proposal=proposal,
        trace_result=trace_result,
        behavior_result=BehavioralSmokeVerifier().verify(proposal=proposal, objective="", success_criteria=[]),
    )

    assert result.validation_evidence[0].validation_stage == "requirement_trace"
    assert result.validation_evidence[0].evidence_type == "test"
    assert result.validation_evidence[0].source_file == "tests/test_math_helpers.py"


def test_behavioral_smoke_does_not_extract_and_as_function_name():
    proposal = _proposal([
        {
            "operation": "create_file",
            "path": "utils/math_helpers.py",
            "content": "def add(a, b):\n    return a + b\n",
        }
    ])

    result = BehavioralSmokeVerifier().verify(
        proposal=proposal,
        objective="Create utils/math_helpers.py with an add function and create pytest tests for it.",
    )

    assert result.passed
    assert [check.expected for check in result.checks if check.check_type == "required_function"] == ["add"]
