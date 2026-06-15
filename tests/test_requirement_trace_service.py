from services.requirement_trace_service import RequirementTraceService


def build_proposal(changes):
    return {
        "result_type": "patch_proposal",
        "objective": 'smoke_message returns "create_file smoke passed"',
        "summary": "test summary",
        "changes": changes,
    }


def test_requirement_trace_generated_for_success_criteria():
    svc = RequirementTraceService()
    proposal = build_proposal([
        {
            "operation": "create_file",
            "path": "services/smoke_service.py",
            "content": 'def smoke_message():\n    return "create_file smoke passed"\n',
        },
        {
            "operation": "create_file",
            "path": "tests/test_smoke_service.py",
            "content": 'from services.smoke_service import smoke_message\n\ndef test_smoke_message():\n    assert smoke_message() == "create_file smoke passed"\n',
        },
    ])

    result = svc.validate(
        proposal=proposal,
        success_criteria=['smoke_message returns "create_file smoke passed"'],
    )

    assert result.passed
    assert result.traces[0].implementation_evidence
    assert result.traces[0].test_evidence
    assert result.traces[0].implementation_evidence[0].file_path == "services/smoke_service.py"
    assert result.traces[0].test_evidence[0].file_path == "tests/test_smoke_service.py"


def test_requirement_trace_rejects_missing_implementation_evidence():
    svc = RequirementTraceService()
    proposal = build_proposal([
        {
            "operation": "create_file",
            "path": "tests/test_smoke_service.py",
            "content": 'def test_smoke_message():\n    assert "create_file smoke passed"\n',
        },
    ])

    result = svc.validate(
        proposal=proposal,
        success_criteria=['smoke_message returns "create_file smoke passed"'],
    )

    assert not result.passed
    assert {violation.code for violation in result.violations} == {
        "MISSING_IMPLEMENTATION_EVIDENCE"
    }


def test_requirement_trace_rejects_missing_test_evidence():
    svc = RequirementTraceService()
    proposal = build_proposal([
        {
            "operation": "create_file",
            "path": "services/smoke_service.py",
            "content": 'def smoke_message():\n    return "create_file smoke passed"\n',
        },
    ])

    result = svc.validate(
        proposal=proposal,
        success_criteria=['smoke_message returns "create_file smoke passed"'],
        require_test_evidence=True,
    )

    assert not result.passed
    assert {violation.code for violation in result.violations} == {
        "MISSING_TEST_EVIDENCE"
    }


def test_requirement_trace_summary_is_manifest_ready():
    svc = RequirementTraceService()
    proposal = build_proposal([
        {
            "operation": "create_file",
            "path": "services/smoke_service.py",
            "content": 'def smoke_message():\n    return "create_file smoke passed"\n',
        },
        {
            "operation": "create_file",
            "path": "tests/test_smoke_service.py",
            "content": 'def test_smoke_message():\n    assert "create_file smoke passed"\n',
        },
    ])

    result = svc.validate(
        proposal=proposal,
        success_criteria=['smoke_message returns "create_file smoke passed"'],
    )
    summary = svc.summarize(result)

    assert summary["requirements"] == 1
    assert summary["traced"] == 1
    assert summary["missing"] == 0
    assert summary["traces"][0]["requirement_id"] == "REQ-001"
