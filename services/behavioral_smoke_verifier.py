from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from services.proposal_quality_service import ProposalQualityService


class BehavioralSmokeViolation(BaseModel):
    code: str
    message: str
    expected: str | None = None
    actual: str | None = None
    instruction: str | None = None


class BehavioralSmokeCheck(BaseModel):
    check_type: Literal["required_literal", "required_function"]
    expected: str
    matched_files: list[str] = Field(default_factory=list)


class BehavioralSmokeResult(BaseModel):
    status: Literal["pass", "fail"]
    checks: list[BehavioralSmokeCheck] = Field(default_factory=list)
    violations: list[BehavioralSmokeViolation] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "pass"


class BehavioralSmokeVerifier:
    """Deterministic, inexpensive behavior checks over proposed content."""

    def __init__(self) -> None:
        self._quality_helper = ProposalQualityService(".")

    def verify(
        self,
        *,
        proposal: dict[str, Any],
        objective: str,
        success_criteria: list[str] | None = None,
    ) -> BehavioralSmokeResult:
        sources = [objective, *(success_criteria or [])]
        changes = [
            change for change in proposal.get("changes", [])
            if isinstance(change, dict)
        ]
        checks: list[BehavioralSmokeCheck] = []
        violations: list[BehavioralSmokeViolation] = []

        for literal in sorted(self._quality_helper._extract_required_literals(sources)):
            matched_files = [
                str(change.get("path"))
                for change in changes
                if literal in str(change.get("content", ""))
                and isinstance(change.get("path"), str)
            ]
            checks.append(
                BehavioralSmokeCheck(
                    check_type="required_literal",
                    expected=literal,
                    matched_files=matched_files,
                )
            )
            if not matched_files:
                actual = self._nearest_quoted_literal(changes) or "<missing>"
                violations.append(
                    BehavioralSmokeViolation(
                        code="REQUIRED_LITERAL_MISSING",
                        message=f"Required literal was not demonstrated in proposed behavior: {literal!r}.",
                        expected=literal,
                        actual=actual,
                        instruction="Preserve requested literal exactly.",
                    )
                )

        for function_name in sorted(self._extract_expected_function_names(sources)):
            matched_files = [
                str(change.get("path"))
                for change in changes
                if re.search(rf"\bdef\s+{re.escape(function_name)}\s*\(", str(change.get("content", "")))
                and isinstance(change.get("path"), str)
            ]
            checks.append(
                BehavioralSmokeCheck(
                    check_type="required_function",
                    expected=function_name,
                    matched_files=matched_files,
                )
            )
            if not matched_files:
                violations.append(
                    BehavioralSmokeViolation(
                        code="REQUIRED_FUNCTION_MISSING",
                        message=f"Required function was not found: {function_name}.",
                        expected=function_name,
                        actual="<missing>",
                        instruction="Implement the requested function with the exact name.",
                    )
                )

        return BehavioralSmokeResult(
            status="fail" if violations else "pass",
            checks=checks,
            violations=violations,
        )

    def _extract_expected_function_names(self, sources: list[str]) -> set[str]:
        names: set[str] = set()
        for source in sources:
            if not isinstance(source, str):
                continue
            for match in re.finditer(r"\b([a-zA-Z_]\w*)\s+returns\b", source):
                names.add(match.group(1))
            for match in re.finditer(r"\bfunction\s+([a-zA-Z_]\w*)\b", source, re.IGNORECASE):
                names.add(match.group(1))
        return names

    def _nearest_quoted_literal(self, changes: list[dict[str, Any]]) -> str | None:
        for change in changes:
            content = str(change.get("content", ""))
            match = re.search(r"return\s+(['\"])(.*?)\1", content)
            if match:
                return match.group(2)
        return None
