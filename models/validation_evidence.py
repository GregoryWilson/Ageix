from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ValidationEvidence(BaseModel):
    requirement_id: str
    test_identifier: str
    status: Literal["PASS", "FAIL", "UNKNOWN"]
    verification_source: str
    timestamp: str
    details: str | None = None


class ValidationEvidenceViolation(BaseModel):
    code: str
    message: str
    requirement_id: str | None = None
    expected: str | None = None
    actual: str | None = None
    instruction: str | None = None


class ValidationEvidenceResult(BaseModel):
    status: Literal["pass", "fail"]
    validation_evidence: list[ValidationEvidence] = Field(default_factory=list)
    violations: list[ValidationEvidenceViolation] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "pass"
