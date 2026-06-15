from __future__ import annotations

import ast
import re
import sys
import tomllib
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
                        instruction="Only modify files explicitly listed in target_files, or request expanded target_files.",
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
                        actual="<missing>",
                        instruction="Include a change for every requested target_file.",
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
                        actual=self._nearest_literal(combined_content),
                        instruction="Preserve requested literal exactly.",
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
                        actual="<missing>",
                        instruction="Represent each success criterion in implementation or test content.",
                    )
                )

            requirement_trace.append(trace)

        research_required = False
        escalation_recommended = False
        escalation: dict[str, Any] = {}

        allowed_dependencies = self._load_allowed_dependencies()

        for change in changes:
            path = change.get("path")
            content = change.get("content")
            if not isinstance(path, str) or not isinstance(content, str):
                continue

            placeholder_violation = self._validate_placeholder_content(path, content)
            if placeholder_violation:
                violations.append(placeholder_violation)

            if path.endswith(".py"):
                tree = None
                try:
                    tree = ast.parse(content)
                except SyntaxError as ex:
                    violations.append(
                        ProposalQualityViolation(
                            code=ProposalQualityFailureCode.PYTHON_SYNTAX_ERROR,
                            message=f"Python content does not compile: {ex.msg} at line {ex.lineno}.",
                            file_path=path,
                            actual=str(ex),
                        instruction="Return syntactically valid Python content for the full file.",
                        )
                    )

                if tree is not None:
                    for import_name in self._iter_import_roots(tree):
                        if self._is_supported_import(import_name, allowed_dependencies):
                            continue

                        violations.append(
                            ProposalQualityViolation(
                                code=ProposalQualityFailureCode.UNSUPPORTED_DEPENDENCY_REFERENCE,
                                message=f"Unsupported dependency reference in {path}: {import_name}.",
                                file_path=path,
                                actual=import_name,
                                instruction="Remove unsupported dependencies or add explicit dependency manifest evidence before referencing them.",
                            )
                        )

                        if self._looks_like_external_api(import_name, objective, content):
                            research_required = True
                            escalation_recommended = True
                            escalation = {
                                "recommended": True,
                                "reason": "External API usage could not be verified from repository evidence.",
                                "target": "research",
                            }

            if self._is_test_path(path) and not self._has_meaningful_assertion(content):
                violations.append(
                    ProposalQualityViolation(
                        code=ProposalQualityFailureCode.TEST_WITHOUT_ASSERTION,
                        message=f"Test file contains no meaningful assertions: {path}.",
                        file_path=path,
                    )
                )

        if not escalation and self._objective_mentions_external_api(objective):
            known_content = combined_content.lower()
            if not any(name.lower() in known_content for name in allowed_dependencies):
                research_required = True
                escalation_recommended = True
                escalation = {
                    "recommended": True,
                    "reason": "External API usage could not be verified from repository evidence.",
                    "target": "research",
                }

        return ProposalQualityResult(
            status="fail" if violations else "pass",
            violations=violations,
            requirement_trace=requirement_trace,
            research_required=research_required,
            escalation_recommended=escalation_recommended,
            escalation=escalation,
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
                    instruction="Replace placeholder or stub content with complete implementation.",
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

    def _nearest_literal(self, content: str) -> str | None:
        match = _QUOTED_LITERAL_PATTERN.search(content)
        if match:
            return match.group(2)
        return None

    def _iter_import_roots(self, tree: ast.AST) -> list[str]:
        roots: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root not in roots:
                        roots.append(root)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                if node.module:
                    root = node.module.split(".")[0]
                    if root not in roots:
                        roots.append(root)
        return roots

    def _is_supported_import(self, root: str, allowed_dependencies: set[str]) -> bool:
        if root in sys.builtin_module_names:
            return True
        if root in getattr(sys, "stdlib_module_names", set()):
            return True
        if root in allowed_dependencies:
            return True
        if self._is_repository_module(root):
            return True
        return False

    def _is_repository_module(self, root: str) -> bool:
        return (self.repo_root / f"{root}.py").exists() or (
            (self.repo_root / root).is_dir()
            and (self.repo_root / root / "__init__.py").exists()
        )

    def _load_allowed_dependencies(self) -> set[str]:
        dependencies: set[str] = set()
        dependencies.update(self._read_requirements_txt())
        dependencies.update(self._read_pyproject_dependencies())
        dependencies.update(self._read_dependency_allowlist())
        return dependencies

    def _read_requirements_txt(self) -> set[str]:
        path = self.repo_root / "requirements.txt"
        if not path.exists():
            return set()
        deps: set[str] = set()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            cleaned = line.strip()
            if not cleaned or cleaned.startswith("#") or cleaned.startswith("-"):
                continue
            name = re.split(r"[<>=!~;\[]", cleaned, maxsplit=1)[0].strip()
            if name:
                deps.add(self._normalize_dependency_name(name))
        return deps

    def _read_pyproject_dependencies(self) -> set[str]:
        path = self.repo_root / "pyproject.toml"
        if not path.exists():
            return set()
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return set()

        raw_deps: list[str] = []
        project = data.get("project", {})
        if isinstance(project.get("dependencies"), list):
            raw_deps.extend(str(item) for item in project["dependencies"])
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for values in optional.values():
                if isinstance(values, list):
                    raw_deps.extend(str(item) for item in values)

        poetry_deps = (
            data.get("tool", {})
            .get("poetry", {})
            .get("dependencies", {})
        )
        if isinstance(poetry_deps, dict):
            raw_deps.extend(str(key) for key in poetry_deps if key.lower() != "python")

        deps: set[str] = set()
        for item in raw_deps:
            name = re.split(r"[<>=!~;\[]", item.strip(), maxsplit=1)[0].strip()
            if name:
                deps.add(self._normalize_dependency_name(name))
        return deps

    def _read_dependency_allowlist(self) -> set[str]:
        candidates = [
            self.repo_root / ".ageix" / "config" / "dependency_allowlist.txt",
            self.repo_root / ".ageix" / "dependency_allowlist.txt",
        ]
        deps: set[str] = set()
        for path in candidates:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                cleaned = line.strip()
                if cleaned and not cleaned.startswith("#"):
                    deps.add(self._normalize_dependency_name(cleaned))
        return deps

    def _normalize_dependency_name(self, name: str) -> str:
        return name.strip().lower().replace("-", "_")

    def _objective_mentions_external_api(self, objective: str) -> bool:
        lowered = objective.lower()
        return any(term in lowered for term in [" api", "library", "sdk", "octoprint", "octopi", "external"])

    def _looks_like_external_api(self, import_name: str, objective: str, content: str) -> bool:
        lowered = " ".join([objective, content, import_name]).lower()
        if import_name in {"dependency_injection"}:
            return False
        return self._objective_mentions_external_api(lowered)
