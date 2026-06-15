from services.behavioral_smoke_verifier import BehavioralSmokeVerifier
from services.requirement_trace_service import RequirementTraceService
from services.validation_evidence_service import ValidationEvidenceService


def build_proposal(changes):
    return {
        "result_type": "patch_proposal",
        "objective": 'smoke_message returns "create_file smoke passed"',
        "summary": "test summary",
        "changes": changes,
    }


def valid_changes():
    return [
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
    ]


def build_trace_and_behavior(proposal):
    criteria = ['smoke_message returns "create_file smoke passed"']
    trace_result = RequirementTraceService().validate(
        proposal=proposal,
        success_criteria=criteria,
        require_test_evidence=True,
    )
    behavior_result = BehavioralSmokeVerifier().verify(
        proposal=proposal,
        objective=proposal["objective"],
        success_criteria=criteria,
    )
    return trace_result, behavior_result


def test_validation_evidence_generated_and_attached_to_trace():
    proposal = build_proposal(valid_changes())
    trace_result, behavior_result = build_trace_and_behavior(proposal)

    result = ValidationEvidenceService().validate(
        proposal=proposal,
        trace_result=trace_result,
        behavior_result=behavior_result,
    )

    assert result.passed
    assert result.validation_evidence
    assert result.validation_evidence[0].requirement_id == "REQ-001"
    assert result.validation_evidence[0].status == "PASS"
    assert trace_result.traces[0].validation_evidence


def test_missing_validation_evidence_rejected():
    proposal = build_proposal(valid_changes())
    trace_result, _ = build_trace_and_behavior(proposal)

    violations = ValidationEvidenceService().validate_coverage(
        proposal=proposal,
        traces=trace_result.traces,
    )

    assert "MISSING_VALIDATION_EVIDENCE" in {violation.code for violation in violations}


def test_missing_test_coverage_rejected():
    proposal = build_proposal([
        {
            "operation": "create_file",
            "path": "services/smoke_service.py",
            "content": 'def smoke_message():\n    return "create_file smoke passed"\n',
        }
    ])
    trace_result = RequirementTraceService().validate(
        proposal=proposal,
        success_criteria=['smoke_message returns "create_file smoke passed"'],
        require_test_evidence=False,
    )

    result = ValidationEvidenceService().validate(
        proposal=proposal,
        trace_result=trace_result,
    )

    assert not result.passed
    assert "MISSING_TEST_EVIDENCE" in {violation.code for violation in result.violations}


def test_failed_validation_evidence_rejected_when_behavior_fails():
    proposal = build_proposal(valid_changes())
    trace_result, _ = build_trace_and_behavior(proposal)
    failed_behavior = BehavioralSmokeVerifier().verify(
        proposal=proposal,
        objective='smoke_message returns "different literal"',
        success_criteria=['smoke_message returns "different literal"'],
    )

    result = ValidationEvidenceService().validate(
        proposal=proposal,
        trace_result=trace_result,
        behavior_result=failed_behavior,
    )

    assert not result.passed
    assert "FAILED_VALIDATION_EVIDENCE" in {violation.code for violation in result.violations}


def test_unmapped_test_evidence_rejected():
    changes = valid_changes() + [
        {
            "operation": "create_file",
            "path": "tests/test_unrelated.py",
            "content": "def test_unrelated():\n    assert True\n",
        }
    ]
    proposal = build_proposal(changes)
    trace_result, behavior_result = build_trace_and_behavior(proposal)

    result = ValidationEvidenceService().validate(
        proposal=proposal,
        trace_result=trace_result,
        behavior_result=behavior_result,
    )

    assert not result.passed
    assert "UNMAPPED_TEST_EVIDENCE" in {violation.code for violation in result.violations}


def test_validation_summary_is_manifest_ready():
    proposal = build_proposal(valid_changes())
    trace_result, behavior_result = build_trace_and_behavior(proposal)
    result = ValidationEvidenceService().validate(
        proposal=proposal,
        trace_result=trace_result,
        behavior_result=behavior_result,
    )

    summary = ValidationEvidenceService().summarize(result)

    assert summary["status"] == "pass"
    assert summary["requirements"] == 1
    assert summary["evidence_count"] == 1
    assert summary["unmapped_test_evidence"] == 0


def test_validation_evidence_includes_runtime_results():
    proposal = build_proposal(valid_changes())
    trace_result, behavior_result = build_trace_and_behavior(proposal)
    from models.test_execution_evidence import (
        TestExecutionEvidence,
        TestExecutionResult,
        TestExecutionStatus,
    )

    runtime_result = TestExecutionResult(
        status='pass',
        runtime_evidence=[
            TestExecutionEvidence(
                test_identifier='tests/test_smoke_service.py',
                status=TestExecutionStatus.PASSED,
                duration_seconds=0.01,
                timestamp='2026-06-15T00:00:00+00:00',
            )
        ],
    )

    result = ValidationEvidenceService().validate(
        proposal=proposal,
        trace_result=trace_result,
        behavior_result=behavior_result,
        runtime_result=runtime_result,
        require_runtime_evidence=True,
    )

    assert result.passed
    assert result.validation_evidence[0].runtime_evidence
    assert result.validation_evidence[0].runtime_evidence[0].status == 'passed'


def test_validation_evidence_requires_runtime_when_requested():
    proposal = build_proposal(valid_changes())
    trace_result, behavior_result = build_trace_and_behavior(proposal)

    result = ValidationEvidenceService().validate(
        proposal=proposal,
        trace_result=trace_result,
        behavior_result=behavior_result,
        require_runtime_evidence=True,
    )

    assert not result.passed
    assert 'NO_RUNTIME_EVIDENCE' in {violation.code for violation in result.violations}
