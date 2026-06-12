from models.proposal_quality_models import ProposalQualityFailureCode
from services.proposal_quality_service import ProposalQualityService


def build_proposal(changes):
    return {
        "result_type": "patch_proposal",
        "objective": "test objective",
        "summary": "test summary",
        "changes": changes,
    }


def test_proposal_validator_accepts_exact_requested_literal():
    svc = ProposalQualityService(".")
    proposal = build_proposal([
        {
            "operation": "create_file",
            "path": "services/smoke_service.py",
            "content": "def smoke_message():\n    return \"create_file smoke passed\"\n",
        }
    ])

    result = svc.validate(
        proposal=proposal,
        objective='smoke_message returns "create_file smoke passed"',
        target_files=["services/smoke_service.py"],
        success_criteria=['smoke_message returns "create_file smoke passed"'],
    )

    assert result.passed


def test_proposal_validator_rejects_changed_requested_literal():
    svc = ProposalQualityService(".")
    proposal = build_proposal([
        {
            "operation": "create_file",
            "path": "services/smoke_service.py",
            "content": "def smoke_message():\n    return \"Smoke test successful!\"\n",
        },
        {
            "operation": "create_file",
            "path": "tests/test_smoke_service.py",
            "content": "from services.smoke_service import smoke_message\n\ndef test_smoke_message():\n    assert smoke_message() == \"Smoke test successful!\"\n",
        },
    ])

    result = svc.validate(
        proposal=proposal,
        objective='smoke_message returns "create_file smoke passed"',
        target_files=["services/smoke_service.py", "tests/test_smoke_service.py"],
        success_criteria=['smoke_message returns "create_file smoke passed"'],
    )

    assert not result.passed
    assert ProposalQualityFailureCode.REQUIRED_LITERAL_MISSING in {
        violation.code for violation in result.violations
    }


def test_proposal_validator_rejects_changes_outside_target_files():
    svc = ProposalQualityService(".")
    proposal = build_proposal([
        {
            "operation": "create_file",
            "path": "services/allowed.py",
            "content": "VALUE = \"ok\"\n",
        },
        {
            "operation": "create_file",
            "path": "services/unrequested.py",
            "content": "VALUE = \"not ok\"\n",
        },
    ])

    result = svc.validate(
        proposal=proposal,
        objective="Create allowed file",
        target_files=["services/allowed.py"],
        success_criteria=[],
    )

    assert not result.passed
    assert ProposalQualityFailureCode.UNAUTHORIZED_FILE_CHANGE in {
        violation.code for violation in result.violations
    }


def test_proposal_validator_requires_requested_target_files_to_appear():
    svc = ProposalQualityService(".")
    proposal = build_proposal([
        {
            "operation": "create_file",
            "path": "services/one.py",
            "content": "VALUE = \"one\"\n",
        },
    ])

    result = svc.validate(
        proposal=proposal,
        objective="Create both files",
        target_files=["services/one.py", "services/two.py"],
        success_criteria=[],
    )

    assert not result.passed
    assert ProposalQualityFailureCode.REQUIRED_TARGET_FILE_MISSING in {
        violation.code for violation in result.violations
    }


def test_proposal_validator_compiles_python_content():
    svc = ProposalQualityService(".")
    proposal = build_proposal([
        {
            "operation": "create_file",
            "path": "services/broken.py",
            "content": "def broken(:\n    return 1\n",
        }
    ])

    result = svc.validate(
        proposal=proposal,
        objective="Create broken file",
        target_files=["services/broken.py"],
        success_criteria=[],
    )

    assert not result.passed
    assert ProposalQualityFailureCode.PYTHON_SYNTAX_ERROR in {
        violation.code for violation in result.violations
    }


def test_proposal_validator_rejects_test_without_assertions():
    svc = ProposalQualityService(".")
    proposal = build_proposal([
        {
            "operation": "create_file",
            "path": "tests/test_empty.py",
            "content": "def test_empty():\n    value = 1\n",
        }
    ])

    result = svc.validate(
        proposal=proposal,
        objective="Create meaningful test",
        target_files=["tests/test_empty.py"],
        success_criteria=[],
    )

    assert not result.passed
    assert ProposalQualityFailureCode.TEST_WITHOUT_ASSERTION in {
        violation.code for violation in result.violations
    }


def test_proposal_validator_rejects_assert_true_placeholder():
    svc = ProposalQualityService(".")
    proposal = build_proposal([
        {
            "operation": "create_file",
            "path": "tests/test_placeholder.py",
            "content": "def test_placeholder():\n    assert True\n",
        }
    ])

    result = svc.validate(
        proposal=proposal,
        objective="Create meaningful test",
        target_files=["tests/test_placeholder.py"],
        success_criteria=[],
    )

    assert not result.passed
    assert ProposalQualityFailureCode.TEST_WITHOUT_ASSERTION in {
        violation.code for violation in result.violations
    }
