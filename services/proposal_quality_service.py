from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from models.proposal_quality_models import (
    ProposalQualityFailureCode,
    ProposalQualityResult,
    ProposalQualityViolation,
    RequirementTrace,
)

_QUOTED_LITERAL_PATTERN = re.compile(r"(['\"])(.+?)\1")


class ProposalQualityService:
    def __init__(self, repo_root: Path | str = ".") -> None:
        self.repo_root = Path(repo_root).resolve()

    def validate(
        self,
        *,
        proposal: dict[str, Any],
        objective: str,
        target_files: list[str],
        success_criteria: list[str] | None = None,
        allow_additional_files: bool = False,
    ) -> ProposalQualityResult:
        success_criteria = success_criteria or []
        changes = proposal.get("changes", [])
        violations: list[ProposalQualityViolation] = []
        requirement_trace: list[RequirementTrace] = []

        changed_paths = [
            change.get("path")
            for change in changes
            if isinstance(change.get("path"), str)
        ]
        changed_path_set = set(changed_paths)
        target_file_set = set(target_files or [])

        if target_file_set and not allow_additional_files:
            for path in changed_paths:
                if not self._matches_target(path, target_file_set):
                    violations.append(
                        ProposalQualityViolation(
                            code=ProposalQualityFailureCode.UNAUTHORIZED_FILE_CHANGE,
                            message=f"Proposal changes {path}, which is not in target_files.",
                            file_path=path,
                            expected=", ".join(sorted(target_file_set)),
                            actual=path,
                        )
                    )

        for path in sorted(target_file_set):
            if not self._target_is_covered(path, changed_path_set):
                violations.append(
                    ProposalQualityViolation(
                        code=ProposalQualityFailureCode.REQUIRED_TARGET_FILE_MISSING,
                        message=f"Requested target_file was not modified: {path}.",
                        file_path=path,
                        expected=path,
                    )
                )

        combined_content = "\n".join(
            str(change.get("content", "")) for change in changes
        )
        required_literals = self._extract_required_literals(
            [objective, *success_criteria]
        )

        for literal in sorted(required_literals):
            if literal not in combined_content:
                violations.append(
                    ProposalQualityViolation(
                        code=ProposalQualityFailureCode.REQUIRED_LITERAL_MISSING,
                        message=f"Required literal not found in proposed content: {literal!r}.",
                        expected=literal,
                    )
                )

        for criterion in success_criteria:
            trace = RequirementTrace(criterion=criterion)
            criterion_literals = self._extract_required_literals([criterion])

            for literal in criterion_literals:
                impl_files = [
                    change["path"]
                    for change in changes
                    if isinstance(change.get("path"), str)
                    and not self._is_test_path(change["path"])
                    and literal in str(change.get("content", ""))
                ]
                test_files = [
                    change["path"]
                    for change in changes
                    if isinstance(change.get("path"), str)
                    and self._is_test_path(change["path"])
                    and literal in str(change.get("content", ""))
                ]
                trace.implementation_evidence.extend(impl_files)
                trace.test_evidence.extend(test_files)

            if criterion_literals and not (
                trace.implementation_evidence or trace.test_evidence
            ):
                violations.append(
                    ProposalQualityViolation(
                        code=ProposalQualityFailureCode.SUCCESS_CRITERIA_NOT_ADDRESSED,
                        message=f"Success criterion is not represented in proposed changes: {criterion}",
                        expected=criterion,
                    )
                )

            requirement_trace.append(trace)

        for change in changes:
            path = change.get("path")
            content = change.get("content")
            if not isinstance(path, str) or not isinstance(content, str):
                continue

            placeholder_violation = self._validate_placeholder_content(path, content)
            if placeholder_violation:
                violations.append(placeholder_violation)

            if path.endswith(".py"):
                try:
                    ast.parse(content)
                except SyntaxError as ex:
                    violations.append(
                        ProposalQualityViolation(
                            code=ProposalQualityFailureCode.PYTHON_SYNTAX_ERROR,
                            message=f"Python content does not compile: {ex.msg} at line {ex.lineno}.",
                            file_path=path,
                            actual=str(ex),
                        )
                    )

            if self._is_test_path(path) and not self._has_meaningful_assertion(content):
                violations.append(
                    ProposalQualityViolation(
                        code=ProposalQualityFailureCode.TEST_WITHOUT_ASSERTION,
                        message=f"Test file contains no meaningful assertions: {path}.",
                        file_path=path,
                    )
                )

        return ProposalQualityResult(
            status="fail" if violations else "pass",
            violations=violations,
            requirement_trace=requirement_trace,
        )

    def _extract_required_literals(self, sources: list[str]) -> set[str]:
        literals: set[str] = set()
        for source in sources:
            if not isinstance(source, str):
                continue
            for match in _QUOTED_LITERAL_PATTERN.finditer(source):
                literal = match.group(2).strip()
                if literal:
                    literals.add(literal)
        return literals

    def _matches_target(self, path: str, targets: set[str]) -> bool:
        for target in targets:
            if path == target:
                return True
            if target.endswith("/") and path.startswith(target):
                return True
        return False

    def _target_is_covered(self, target: str, changed_paths: set[str]) -> bool:
        if target in changed_paths:
            return True
        if target.endswith("/"):
            return any(path.startswith(target) for path in changed_paths)
        return False

    def _validate_placeholder_content(
        self,
        path: str,
        content: str,
    ) -> ProposalQualityViolation | None:
        lowered = content.lower()
        forbidden_markers = [
            "<new file content",
            "<placeholder",
            "todo",
            "pass\n",
            "pass\r\n",
            "based on requirements",
        ]

        for marker in forbidden_markers:
            if marker in lowered:
                return ProposalQualityViolation(
                    code=ProposalQualityFailureCode.PLACEHOLDER_CONTENT,
                    message=f"{path} contains placeholder/stub content.",
                    file_path=path,
                    actual=marker,
                )

        return None

    def _is_test_path(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        name = Path(normalized).name
        return normalized.startswith("tests/") or name.startswith("test_")

    def _has_meaningful_assertion(self, content: str) -> bool:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return "assert " in content

        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                if isinstance(node.test, ast.Constant) and node.test.value is True:
                    continue
                return True

            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr.startswith("assert"):
                    if func.attr == "assertTrue" and node.args:
                        first_arg = node.args[0]
                        if isinstance(first_arg, ast.Constant) and first_arg.value is True:
                            continue
                    return True

        return False
