from chair import build_assertion_diagnostics, has_test_assertion, validate_no_placeholder_patch_content
from services.requirement_trace_service import RequirementTraceService
from services.validation_evidence_service import ValidationEvidenceService


def _proposal(changes):
    return {
        "result_type": "patch_proposal",
        "objective": "Create utils/math_helpers.py with an add function and create pytest tests for it.",
        "summary": "Create math helper and tests",
        "changes": changes,
    }


def test_chair_accepts_self_assert_equal():
    content = """import unittest

class TestFormatter(unittest.TestCase):
    def test_format_confidence(self):
        self.assertEqual('50%', '50%')
"""

    validate_no_placeholder_patch_content("tests/test_formatter.py", content)
    assert has_test_assertion(content) is True
    assert build_assertion_diagnostics(content)["unittest_assert_count"] == 1


def test_chair_accepts_self_assert_true_with_non_literal_expression():
    content = """import unittest

class TestFormatter(unittest.TestCase):
    def test_format_confidence(self):
        self.assertTrue('50%'.endswith('%'))
"""

    validate_no_placeholder_patch_content("tests/test_formatter.py", content)
    assert has_test_assertion(content) is True


def test_chair_accepts_self_assert_raises():
    content = """import unittest

class TestFormatter(unittest.TestCase):
    def test_format_confidence(self):
        with self.assertRaises(ValueError):
            raise ValueError('bad')
"""

    validate_no_placeholder_patch_content("tests/test_formatter.py", content)
    assert has_test_assertion(content) is True


def test_chair_accepts_pytest_raises():
    content = """import pytest

def test_format_confidence():
    with pytest.raises(ValueError):
        raise ValueError('bad')
"""

    validate_no_placeholder_patch_content("tests/test_formatter.py", content)
    assert has_test_assertion(content) is True
    assert build_assertion_diagnostics(content)["pytest_raises_count"] == 1


def test_chair_rejects_test_without_assertion_with_diagnostics():
    content = """def test_placeholder():
    value = 1 + 1
"""

    try:
        validate_no_placeholder_patch_content("tests/test_placeholder.py", content)
    except ValueError as ex:
        assert "contains no assertions" in str(ex)
        assert "diagnostics=" in str(ex)
    else:
        raise AssertionError("Expected missing assertion failure")


def test_validation_evidence_does_not_require_behavioral_test_for_authorized_file_existence_trace():
    proposal = _proposal([
        {
            "operation": "create_file",
            "path": "utils/math_helpers.py",
            "content": "def add(a, b):\n    return a + b\n",
        },
        {
            "operation": "create_file",
            "path": "tests/test_math_helpers.py",
            "content": "from utils.math_helpers import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        },
    ])
    trace_result = RequirementTraceService().validate(
        proposal=proposal,
        success_criteria=[
            "Authorized target file exists in proposal: utils/math_helpers.py",
            "Executable test target exists: tests/test_math_helpers.py",
        ],
    )

    result = ValidationEvidenceService().validate(
        proposal=proposal,
        trace_result=trace_result,
        require_runtime_evidence=False,
    )

    assert "MISSING_TEST_EVIDENCE" not in {violation.code for violation in result.violations}


def test_validation_evidence_reports_trace_diagnostics_for_real_missing_test_evidence():
    proposal = _proposal([
        {
            "operation": "create_file",
            "path": "utils/math_helpers.py",
            "content": "def add(a, b):\n    return a + b\n",
        }
    ])
    trace_result = RequirementTraceService().validate(
        proposal=proposal,
        success_criteria=["Implementation returns the sum of two numbers"],
        require_test_evidence=False,
    )

    result = ValidationEvidenceService().validate(
        proposal=proposal,
        trace_result=trace_result,
        require_runtime_evidence=False,
    )

    assert result.status == "fail"
    violation = result.violations[0]
    assert violation.code == "MISSING_TEST_EVIDENCE"
    assert "implementation_evidence_count" in violation.actual
    assert "requires_mapped_test_evidence" in violation.actual
