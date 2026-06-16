from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from models.validation_evidence import (
    ValidationEvidence,
    ValidationEvidenceResult,
    ValidationEvidenceViolation,
)
from services.requirement_trace_service import RequirementTrace, RequirementTraceResult
from services.behavioral_smoke_verifier import BehavioralSmokeResult
from models.test_execution_evidence import TestExecutionEvidence, TestExecutionResult, TestExecutionStatus


class ValidationEvidenceService:
    """Generates and validates requirement-connected validation evidence."""

    def generate(
        self,
        *,
        trace_result: RequirementTraceResult,
        behavior_result: BehavioralSmokeResult | None = None,
        verification_source: str = "behavioral_smoke_verifier",
        runtime_result: TestExecutionResult | None = None,
    ) -> list[ValidationEvidence]:
        timestamp = datetime.now(timezone.utc).isoformat()
        evidence: list[ValidationEvidence] = []
        behavior_status = self._normalize_behavior_status(behavior_result)
        runtime_by_test = self._runtime_evidence_by_test(runtime_result)
        runtime_required = runtime_result is not None

        for trace in trace_result.traces:
            for test in trace.test_evidence:
                test_identifier = self._test_identifier(test)
                runtime_evidence = runtime_by_test.get(test_identifier, [])
                evidence.append(
                    ValidationEvidence(
                        requirement_id=trace.requirement_id,
                        test_identifier=test_identifier,
                        status=self._combined_status(behavior_status, runtime_evidence, runtime_required),
                        verification_source=verification_source,
                        timestamp=timestamp,
                        details=(
                            "Behavioral and runtime verification passed for requirement-connected test evidence."
                            if behavior_status == "PASS" and self._runtime_passed(runtime_evidence)
                            else "Behavioral or runtime verification did not pass for requirement-connected test evidence."
                        ),
                        validation_stage="requirement_trace",
                        evidence_type="test",
                        source_file=test.file_path,
                        runtime_evidence=runtime_evidence,
                    )
                )

        return evidence

    def attach_validation_evidence(
        self,
        *,
        trace_result: RequirementTraceResult,
        validation_evidence: list[ValidationEvidence],
    ) -> RequirementTraceResult:
        evidence_by_requirement: dict[str, list[ValidationEvidence]] = {}
        for evidence in validation_evidence:
            evidence_by_requirement.setdefault(evidence.requirement_id, []).append(evidence)

        for trace in trace_result.traces:
            trace.validation_evidence = evidence_by_requirement.get(trace.requirement_id, [])

        return trace_result

    def validate(
        self,
        *,
        proposal: dict[str, Any],
        trace_result: RequirementTraceResult,
        behavior_result: BehavioralSmokeResult | None = None,
        runtime_result: TestExecutionResult | None = None,
        require_runtime_evidence: bool = False,
    ) -> ValidationEvidenceResult:
        generated = self.generate(
            trace_result=trace_result,
            behavior_result=behavior_result,
            runtime_result=runtime_result,
        )
        self.attach_validation_evidence(
            trace_result=trace_result,
            validation_evidence=generated,
        )

        violations = self.validate_coverage(
            proposal=proposal,
            traces=trace_result.traces,
            require_runtime_evidence=require_runtime_evidence,
        )

        return ValidationEvidenceResult(
            status="fail" if violations else "pass",
            validation_evidence=generated,
            violations=violations,
        )

    def validate_coverage(
        self,
        *,
        proposal: dict[str, Any],
        traces: list[RequirementTrace],
        require_runtime_evidence: bool = False,
    ) -> list[ValidationEvidenceViolation]:
        violations: list[ValidationEvidenceViolation] = []

        for trace in traces:
            if (
                trace.implementation_evidence
                and not trace.test_evidence
                and self._requires_mapped_test_evidence(trace)
            ):
                violations.append(
                    ValidationEvidenceViolation(
                        code="MISSING_TEST_EVIDENCE",
                        message="Requirement has implementation evidence but no mapped test evidence.",
                        requirement_id=trace.requirement_id,
                        expected=trace.requirement_text,
                        actual=str(self._trace_diagnostics(trace, proposed_tests=self._proposal_test_paths(proposal))),
                        instruction="Provide a test that validates the requirement and include trace evidence.",
                    )
                )

            if trace.test_evidence and not trace.validation_evidence:
                violations.append(
                    ValidationEvidenceViolation(
                        code="MISSING_VALIDATION_EVIDENCE",
                        message="Requirement has test evidence but no validation evidence.",
                        requirement_id=trace.requirement_id,
                        expected=trace.requirement_text,
                        actual="<missing>",
                        instruction="Attach validation evidence showing the mapped test was checked.",
                    )
                )

            for evidence in trace.validation_evidence:
                if evidence.status != "PASS":
                    violations.append(
                        ValidationEvidenceViolation(
                            code="FAILED_VALIDATION_EVIDENCE",
                            message="Requirement validation evidence did not pass.",
                            requirement_id=trace.requirement_id,
                            expected="PASS",
                            actual=evidence.status,
                            instruction="Fix the implementation or test so validation evidence passes.",
                        )
                    )

        if require_runtime_evidence:
            for trace in traces:
                for evidence in trace.validation_evidence:
                    if not evidence.runtime_evidence:
                        violations.append(
                        ValidationEvidenceViolation(
                            code="NO_RUNTIME_EVIDENCE",
                            message="Requirement validation evidence has no runtime execution evidence.",
                            requirement_id=trace.requirement_id,
                            expected="Runtime execution evidence attached to validation evidence.",
                            actual="<missing>",
                            instruction="Provide executable test coverage and runtime validation evidence.",
                            )
                        )

        mapped_tests = {
            evidence.file_path
            for trace in traces
            for evidence in trace.test_evidence
            if evidence.file_path
        }
        proposed_tests = self._proposal_test_paths(proposal)

        for test_path in sorted(proposed_tests - mapped_tests):
            violations.append(
                ValidationEvidenceViolation(
                    code="UNMAPPED_TEST_EVIDENCE",
                    message="Proposal contains a test file that is not mapped to any requirement trace.",
                    expected="Every proposed test maps to a requirement.",
                    actual=test_path,
                    instruction="Map each test to a requirement or remove unrelated test changes.",
                )
            )

        return violations


    def _requires_mapped_test_evidence(self, trace: RequirementTrace) -> bool:
        lowered = trace.requirement_text.lower()

        # File-existence acceptance criteria are satisfied by the proposed file
        # change itself. They should not be converted into behavioral coverage
        # requirements merely because the evidence is an implementation file.
        file_existence_markers = [
            "authorized target file exists",
            "target file exists",
            "file exists in proposal",
        ]
        if any(marker in lowered for marker in file_existence_markers):
            return False

        # Meta validation criteria are proved by trace/runtime evidence elsewhere.
        if "requirement trace covers" in lowered or "generated test command passes" in lowered:
            return False

        return True

    def _trace_diagnostics(
        self,
        trace: RequirementTrace,
        *,
        proposed_tests: set[str],
    ) -> dict[str, Any]:
        return {
            "requirement_id": trace.requirement_id,
            "requirement_text": trace.requirement_text,
            "implementation_evidence_count": len(trace.implementation_evidence),
            "test_evidence_count": len(trace.test_evidence),
            "validation_evidence_count": len(trace.validation_evidence),
            "requires_mapped_test_evidence": self._requires_mapped_test_evidence(trace),
            "implementation_sources": [e.file_path for e in trace.implementation_evidence if e.file_path],
            "test_sources": [e.file_path for e in trace.test_evidence if e.file_path],
            "proposed_test_sources": sorted(proposed_tests),
        }

    def summarize(self, result: ValidationEvidenceResult) -> dict[str, Any]:
        violations_by_code: dict[str, int] = {}
        for violation in result.violations:
            violations_by_code[violation.code] = violations_by_code.get(violation.code, 0) + 1

        requirements = {
            evidence.requirement_id
            for evidence in result.validation_evidence
        }
        passed = [
            evidence
            for evidence in result.validation_evidence
            if evidence.status == "PASS"
        ]

        return {
            "status": result.status,
            "requirements": len(requirements),
            "evidence_count": len(result.validation_evidence),
            "passed": len(passed),
            "failed": len(result.validation_evidence) - len(passed),
            "missing_test_evidence": violations_by_code.get("MISSING_TEST_EVIDENCE", 0),
            "missing_validation_evidence": violations_by_code.get("MISSING_VALIDATION_EVIDENCE", 0),
            "failed_validation_evidence": violations_by_code.get("FAILED_VALIDATION_EVIDENCE", 0),
            "unmapped_test_evidence": violations_by_code.get("UNMAPPED_TEST_EVIDENCE", 0),
            "no_runtime_evidence": violations_by_code.get("NO_RUNTIME_EVIDENCE", 0),
            "runtime_evidence_count": sum(len(e.runtime_evidence) for e in result.validation_evidence),
            "violations": [violation.model_dump() for violation in result.violations],
        }

    def _runtime_evidence_by_test(
        self,
        runtime_result: TestExecutionResult | None,
    ) -> dict[str, list[TestExecutionEvidence]]:
        by_test: dict[str, list[TestExecutionEvidence]] = {}
        if runtime_result is None:
            return by_test
        for evidence in runtime_result.runtime_evidence:
            by_test.setdefault(evidence.test_identifier, []).append(evidence)
        return by_test

    def _runtime_passed(self, runtime_evidence: list[TestExecutionEvidence]) -> bool:
        return bool(runtime_evidence) and all(
            evidence.status == TestExecutionStatus.PASSED
            for evidence in runtime_evidence
        )

    def _combined_status(
        self,
        behavior_status: str,
        runtime_evidence: list[TestExecutionEvidence],
        runtime_required: bool = True,
    ) -> str:
        if behavior_status != "PASS":
            return behavior_status
        if not runtime_required:
            return behavior_status
        return "PASS" if self._runtime_passed(runtime_evidence) else "FAIL"

    def _normalize_behavior_status(
        self,
        behavior_result: BehavioralSmokeResult | None,
    ) -> str:
        if behavior_result is None:
            return "UNKNOWN"
        return "PASS" if behavior_result.passed else "FAIL"

    def _test_identifier(self, evidence: Any) -> str:
        return evidence.file_path or "<unknown-test>"

    def _proposal_test_paths(self, proposal: dict[str, Any]) -> set[str]:
        paths: set[str] = set()
        for change in proposal.get("changes", []):
            if not isinstance(change, dict):
                continue
            path = change.get("path")
            if isinstance(path, str) and self._is_test_path(path):
                paths.add(path)
        return paths

    def _is_test_path(self, path: str) -> bool:
        normalized = str(path).replace("\\", "/")
        return normalized.startswith("tests/") or normalized.split("/")[-1].startswith("test_")
