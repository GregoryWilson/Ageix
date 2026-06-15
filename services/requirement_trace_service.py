from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from services.proposal_quality_service import ProposalQualityService
from models.validation_evidence import ValidationEvidence


class RequirementEvidence(BaseModel):
    evidence_type: Literal["implementation", "test", "validation"]
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    description: str


class RequirementTrace(BaseModel):
    requirement_id: str
    requirement_text: str
    implementation_evidence: list[RequirementEvidence] = Field(default_factory=list)
    test_evidence: list[RequirementEvidence] = Field(default_factory=list)
    validation_evidence: list[ValidationEvidence] = Field(default_factory=list)
    status: Literal["traced", "incomplete"] = "incomplete"


class RequirementTraceViolation(BaseModel):
    code: str
    message: str
    requirement_id: str | None = None
    expected: str | None = None
    actual: str | None = None
    instruction: str | None = None


class RequirementTraceResult(BaseModel):
    status: Literal["pass", "fail"]
    traces: list[RequirementTrace] = Field(default_factory=list)
    violations: list[RequirementTraceViolation] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "pass"


class RequirementTraceService:
    """Builds and validates deterministic evidence links for success criteria."""

    def __init__(self) -> None:
        self._quality_helper = ProposalQualityService(".")

    def build_traces(
        self,
        *,
        proposal: dict[str, Any],
        success_criteria: list[str] | None = None,
        validation_summary: dict[str, Any] | None = None,
    ) -> list[RequirementTrace]:
        traces: list[RequirementTrace] = []
        changes = [change for change in proposal.get("changes", []) if isinstance(change, dict)]

        for index, criterion in enumerate(success_criteria or [], start=1):
            trace = RequirementTrace(
                requirement_id=f"REQ-{index:03d}",
                requirement_text=criterion,
            )
            literals = self._quality_helper._extract_required_literals([criterion])
            search_terms = sorted(literals) or [criterion]

            for change in changes:
                path = change.get("path")
                content = change.get("content")
                if not isinstance(path, str) or not isinstance(content, str):
                    continue

                for term in search_terms:
                    line_no = self._find_line(content, term)
                    if line_no is None:
                        continue
                    evidence = RequirementEvidence(
                        evidence_type="test" if self._is_test_path(path) else "implementation",
                        file_path=path,
                        line_start=line_no,
                        line_end=line_no,
                        description=f"Contains evidence for requirement term: {term}",
                    )
                    if evidence.evidence_type == "test":
                        trace.test_evidence.append(evidence)
                    else:
                        trace.implementation_evidence.append(evidence)


            trace.status = "traced" if trace.implementation_evidence and trace.test_evidence else "incomplete"
            traces.append(trace)

        return traces

    def validate(
        self,
        *,
        proposal: dict[str, Any],
        success_criteria: list[str] | None = None,
        validation_summary: dict[str, Any] | None = None,
        require_test_evidence: bool = True,
    ) -> RequirementTraceResult:
        traces = self.build_traces(
            proposal=proposal,
            success_criteria=success_criteria,
            validation_summary=validation_summary,
        )
        violations: list[RequirementTraceViolation] = []

        for trace in traces:
            if not trace.implementation_evidence:
                violations.append(
                    RequirementTraceViolation(
                        code="MISSING_IMPLEMENTATION_EVIDENCE",
                        message="Requirement has no implementation evidence.",
                        requirement_id=trace.requirement_id,
                        expected=trace.requirement_text,
                        actual="<missing>",
                        instruction="Reference a changed implementation file that demonstrates this requirement.",
                    )
                )
            if require_test_evidence and not trace.test_evidence:
                violations.append(
                    RequirementTraceViolation(
                        code="MISSING_TEST_EVIDENCE",
                        message="Requirement has no test evidence.",
                        requirement_id=trace.requirement_id,
                        expected=trace.requirement_text,
                        actual="<missing>",
                        instruction="Add or update a test that asserts the requested behavior.",
                    )
                )

        return RequirementTraceResult(
            status="fail" if violations else "pass",
            traces=traces,
            violations=violations,
        )

    def summarize(self, result: RequirementTraceResult) -> dict[str, Any]:
        return {
            "status": result.status,
            "requirements": len(result.traces),
            "traced": sum(1 for trace in result.traces if trace.status == "traced"),
            "missing": len(result.violations),
            "traces": [trace.model_dump() for trace in result.traces],
            "violations": [violation.model_dump() for violation in result.violations],
        }

    def _find_line(self, content: str, term: str) -> int | None:
        for index, line in enumerate(content.splitlines(), start=1):
            if term in line:
                return index
        return None

    def _is_test_path(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        return normalized.startswith("tests/") or normalized.split("/")[-1].startswith("test_")
