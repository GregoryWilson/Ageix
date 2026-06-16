from __future__ import annotations

from collections import defaultdict, deque
from fnmatch import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from models.dependency_intelligence import DependencyClassification
from models.repository_impact import (
    RepositoryImpactEvidence,
    RepositoryImpactRelationship,
    RepositoryImpactResult,
)
from services.controls_service import ControlsService
from services.dependency_intelligence_service import DependencyIntelligenceService


@dataclass(frozen=True)
class RepositoryImpactControls:
    enabled: bool = True
    max_depth: int = 2
    max_nodes: int = 75
    max_dependents_per_file: int = 25
    retry_on_limit: bool = True
    retry_max_depth: int = 4
    retry_max_nodes: int = 200
    retry_max_dependents_per_file: int = 75
    retry_policy: str = "validation_failure_only"
    include_tests: bool = True
    include_runtime_files: bool = True
    include_companion_tests: bool = True
    impacted_test_depth: int = 1
    auto_add_companion_tests: bool = True
    auto_add_impacted_tests: bool = True
    recommend_indirect_dependents: bool = True
    circular_dependency_policy: str = "warn_stop_path"
    unresolved_import_policy: str = "warn"
    unknown_impact_policy: str = "warn"
    limit_policy: str = "warn"
    exclude_paths: tuple[str, ...] = (
        ".git/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
        "__pycache__/",
        "venv/",
        ".venv/",
        "env/",
        ".env/",
        "site-packages/",
        "node_modules/",
        "build/",
        "dist/",
        "*.egg-info/",
        "artifacts/",
        "htmlcov/",
        ".tox/",
        ".ageix/staged/",
        ".ageix/staging/",
        ".ageix/manifests/",
        ".ageix/runs/",
        ".ageix/runtime/",
        ".ageix/verification/",
        ".ageix/repair_loops/",
        ".ageix/logs/",
    )

    @classmethod
    def from_raw(cls, raw: dict[str, Any] | None) -> "RepositoryImpactControls":
        raw = raw or {}
        return cls(
            enabled=bool(raw.get("enabled", True)),
            max_depth=int(raw.get("max_depth", 2)),
            max_nodes=int(raw.get("max_nodes", 75)),
            max_dependents_per_file=int(raw.get("max_dependents_per_file", 25)),
            retry_on_limit=bool(raw.get("retry_on_limit", True)),
            retry_max_depth=int(raw.get("retry_max_depth", 4)),
            retry_max_nodes=int(raw.get("retry_max_nodes", 200)),
            retry_max_dependents_per_file=int(raw.get("retry_max_dependents_per_file", 75)),
            retry_policy=str(raw.get("retry_policy", "validation_failure_only")),
            include_tests=bool(raw.get("include_tests", True)),
            include_runtime_files=bool(raw.get("include_runtime_files", True)),
            include_companion_tests=bool(raw.get("include_companion_tests", True)),
            impacted_test_depth=int(raw.get("impacted_test_depth", 1)),
            auto_add_companion_tests=bool(raw.get("auto_add_companion_tests", True)),
            auto_add_impacted_tests=bool(raw.get("auto_add_impacted_tests", True)),
            recommend_indirect_dependents=bool(raw.get("recommend_indirect_dependents", True)),
            circular_dependency_policy=str(raw.get("circular_dependency_policy", "warn_stop_path")),
            unresolved_import_policy=str(raw.get("unresolved_import_policy", "warn")),
            unknown_impact_policy=str(raw.get("unknown_impact_policy", "warn")),
            limit_policy=str(raw.get("limit_policy", "warn")),
            exclude_paths=tuple(str(item).replace("\\", "/") for item in raw.get("exclude_paths", cls.exclude_paths)),
        )


class RepositoryImpactService:
    """Builds bounded reverse-dependency impact evidence for repository changes."""

    def __init__(self, repo_root: Path | str = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        raw = ControlsService(self.repo_root).get_raw_config().get("repository_impact", {})
        self.controls = RepositoryImpactControls.from_raw(raw)
        self._dependency_service = DependencyIntelligenceService(self.repo_root)

    def analyze(
        self,
        *,
        target_files: list[str] | None = None,
        proposal: dict[str, Any] | None = None,
        expanded: bool = False,
    ) -> RepositoryImpactResult:
        if not self.controls.enabled:
            return RepositoryImpactResult(status="disabled", summary={"status": "disabled"})

        proposal = proposal or {}
        changed_files = self._merge_strings(target_files or [], self._proposal_paths(proposal))
        changed_files = [path for path in changed_files if path.endswith(".py")]
        if not changed_files:
            return RepositoryImpactResult(summary=self._summary([], [], [], [], expanded, []))

        limits = self._limits(expanded)
        reverse_graph, unresolved = self._build_reverse_graph(proposal)
        evidence: list[RepositoryImpactEvidence] = []
        violations: list[str] = []
        impact_graph: dict[str, list[str]] = defaultdict(list)
        impacted_files: list[str] = []
        impacted_tests: list[str] = []
        companion_files: list[str] = []
        visited_nodes: set[str] = set()

        for unresolved_item in unresolved:
            if self.controls.unresolved_import_policy == "warn":
                violations.append(f"unresolved_dependency: {unresolved_item}")

        for source_file in sorted(changed_files):
            if self.controls.include_companion_tests:
                companion = self._companion_test_file(source_file)
                if companion:
                    companion_files.append(companion)
                    if self.controls.include_tests:
                        impacted_tests.append(companion)
                    evidence.append(RepositoryImpactEvidence(
                        source_file=source_file,
                        impacted_file=companion,
                        relationship=RepositoryImpactRelationship.COMPANION_TEST,
                        depth=1,
                        reason="test filename matches implementation module",
                        confidence=0.9,
                    ))

            queue: deque[tuple[str, int, tuple[str, ...]]] = deque([(source_file, 0, (source_file,))])
            while queue:
                current, depth, path = queue.popleft()
                if depth >= limits["max_depth"]:
                    if reverse_graph.get(current):
                        self._append_violation(violations, "impact_depth_limit_exceeded")
                    continue

                dependents = sorted(reverse_graph.get(current, []))
                if len(dependents) > limits["max_dependents_per_file"]:
                    self._append_violation(violations, "impact_dependents_limit_exceeded")
                    dependents = dependents[: limits["max_dependents_per_file"]]

                for dependent in dependents:
                    if dependent in path:
                        self._append_violation(violations, "circular_dependency_detected")
                        continue
                    next_depth = depth + 1
                    if len(visited_nodes) >= limits["max_nodes"]:
                        self._append_violation(violations, "impact_node_limit_exceeded")
                        queue.clear()
                        break
                    visited_nodes.add(dependent)
                    impact_graph[source_file].append(dependent)
                    relationship = self._relationship_for(dependent, next_depth)
                    confidence = self._confidence_for(relationship, next_depth)
                    reason = self._reason_for(current, dependent, relationship)
                    evidence.append(RepositoryImpactEvidence(
                        source_file=source_file,
                        impacted_file=dependent,
                        relationship=relationship,
                        depth=next_depth,
                        reason=reason,
                        confidence=confidence,
                    ))
                    if dependent not in impacted_files:
                        impacted_files.append(dependent)
                    if relationship == RepositoryImpactRelationship.IMPACTED_TEST and next_depth <= self.controls.impacted_test_depth:
                        impacted_tests.append(dependent)
                    queue.append((dependent, next_depth, (*path, dependent)))

        impacted_files = sorted(dict.fromkeys(impacted_files))
        impacted_tests = sorted(dict.fromkeys(impacted_tests))
        companion_files = sorted(dict.fromkeys(companion_files))
        evidence = sorted(evidence, key=lambda item: (item.source_file, item.depth, item.impacted_file, item.relationship.value))
        normalized_graph = {key: sorted(dict.fromkeys(value)) for key, value in sorted(impact_graph.items())}
        status = "warn" if violations else "pass"
        return RepositoryImpactResult(
            status=status,
            impact_graph=normalized_graph,
            impacted_files=impacted_files,
            impacted_tests=impacted_tests,
            companion_files=companion_files,
            evidence=evidence,
            summary=self._summary(impacted_files, impacted_tests, companion_files, evidence, expanded, violations),
            violations=sorted(dict.fromkeys(violations)),
        )

    def should_retry_expanded(self, result: RepositoryImpactResult) -> bool:
        if not self.controls.retry_on_limit:
            return False
        return any(violation.startswith("impact_") and "limit_exceeded" in violation for violation in result.violations)

    def _build_reverse_graph(self, proposal: dict[str, Any]) -> tuple[dict[str, list[str]], list[str]]:
        proposed_files = self._proposal_python_content(proposal)
        source_files = {**self._repository_python_content(), **proposed_files}
        reverse: dict[str, list[str]] = defaultdict(list)
        unresolved: list[str] = []
        for source_file in sorted(source_files):
            if self._is_test_path(source_file) and not self.controls.include_tests:
                continue
            if not self._is_test_path(source_file) and not self.controls.include_runtime_files:
                continue
            imports = self._dependency_service.parse_imports(source_files[source_file], source_file=source_file)
            for import_name in imports:
                classification, resolved_path = self._dependency_service.classify_dependency(import_name, source_file, proposed_files)
                if classification in {DependencyClassification.EXISTING_REPO_DEPENDENCY, DependencyClassification.PROPOSED_REPO_DEPENDENCY} and resolved_path:
                    reverse[resolved_path].append(source_file)
                elif classification == DependencyClassification.UNKNOWN_EXTERNAL_DEPENDENCY:
                    unresolved.append(f"{source_file}:{import_name}")
        return {key: sorted(dict.fromkeys(value)) for key, value in reverse.items()}, sorted(dict.fromkeys(unresolved))

    def _repository_python_content(self) -> dict[str, str]:
        files: dict[str, str] = {}
        for path in sorted(self.repo_root.rglob("*.py")):
            rel = self._relative_path(path)
            if self._skip_path(rel):
                continue
            files[rel] = path.read_text(encoding="utf-8", errors="replace")
        return files

    def _proposal_python_content(self, proposal: dict[str, Any]) -> dict[str, str]:
        files: dict[str, str] = {}
        for change in proposal.get("changes", []) or []:
            path = change.get("path")
            content = change.get("content")
            if isinstance(path, str) and path.endswith(".py") and isinstance(content, str):
                files[self._normalize_path(path)] = content
        return files

    def _proposal_paths(self, proposal: dict[str, Any]) -> list[str]:
        return [self._normalize_path(change.get("path")) for change in proposal.get("changes", []) or [] if isinstance(change.get("path"), str)]

    def _companion_test_file(self, path: str) -> str | None:
        normalized = self._normalize_path(path)
        if self._is_test_path(normalized) or not normalized.endswith(".py"):
            return None
        name = Path(normalized).stem
        if normalized.startswith("services/"):
            return f"tests/test_{name}.py"
        if normalized.startswith("agents/"):
            if name.endswith("_agent"):
                name = name[:-6]
            return f"tests/test_{name}_agent.py"
        return None

    def _relationship_for(self, path: str, depth: int) -> RepositoryImpactRelationship:
        if self._is_test_path(path):
            return RepositoryImpactRelationship.IMPACTED_TEST
        if depth == 1:
            return RepositoryImpactRelationship.DIRECT_DEPENDENT
        return RepositoryImpactRelationship.INDIRECT_DEPENDENT

    def _reason_for(self, current: str, dependent: str, relationship: RepositoryImpactRelationship) -> str:
        if relationship == RepositoryImpactRelationship.IMPACTED_TEST:
            return f"test imports or depends on impacted module {current}"
        if relationship == RepositoryImpactRelationship.DIRECT_DEPENDENT:
            return f"file imports changed module {current}"
        return f"file depends on downstream impacted module {current}"

    def _confidence_for(self, relationship: RepositoryImpactRelationship, depth: int) -> float:
        if relationship == RepositoryImpactRelationship.COMPANION_TEST:
            return 0.9
        if relationship == RepositoryImpactRelationship.IMPACTED_TEST:
            return 0.85 if depth == 1 else 0.75
        if relationship == RepositoryImpactRelationship.DIRECT_DEPENDENT:
            return 0.85
        return 0.7

    def _summary(
        self,
        impacted_files: list[str],
        impacted_tests: list[str],
        companion_files: list[str],
        evidence: list[RepositoryImpactEvidence],
        expanded: bool,
        violations: list[str],
    ) -> dict[str, Any]:
        confidence_values = [item.confidence for item in evidence]
        confidence = min(confidence_values) if confidence_values else 1.0
        if violations:
            confidence = min(confidence, 0.65)
        return {
            "status": "warn" if violations else "pass",
            "pass": "expanded" if expanded else "initial",
            "impacted_files_count": len(set(impacted_files)),
            "impacted_tests": sorted(dict.fromkeys(impacted_tests)),
            "companion_files": sorted(dict.fromkeys(companion_files)),
            "limits_encountered": sorted(v for v in set(violations) if v.startswith("impact_")),
            "violations": sorted(dict.fromkeys(violations)),
            "confidence": round(confidence, 4),
            "retry_recommended": any(v.startswith("impact_") and "limit_exceeded" in v for v in violations),
        }

    def _limits(self, expanded: bool) -> dict[str, int]:
        if expanded:
            return {
                "max_depth": self.controls.retry_max_depth,
                "max_nodes": self.controls.retry_max_nodes,
                "max_dependents_per_file": self.controls.retry_max_dependents_per_file,
            }
        return {
            "max_depth": self.controls.max_depth,
            "max_nodes": self.controls.max_nodes,
            "max_dependents_per_file": self.controls.max_dependents_per_file,
        }

    def _relative_path(self, path: Path) -> str:
        return self._normalize_path(str(path.relative_to(self.repo_root)))

    def _normalize_path(self, path: str) -> str:
        return str(path).replace("\\", "/").strip("/")

    def _skip_path(self, path: str) -> bool:
        normalized = self._normalize_path(path)
        parts = set(Path(normalized).parts)
        for raw_pattern in self.controls.exclude_paths:
            pattern = self._normalize_path(raw_pattern)
            if not pattern:
                continue
            directory_pattern = pattern.rstrip("/")
            if directory_pattern in parts:
                return True
            if pattern.endswith("/") and (normalized == directory_pattern or normalized.startswith(f"{directory_pattern}/")):
                return True
            if fnmatch(normalized, pattern) or fnmatch(Path(normalized).name, pattern):
                return True
        return False

    def _is_test_path(self, path: str) -> bool:
        normalized = self._normalize_path(path)
        return normalized.startswith("tests/") or Path(normalized).name.startswith("test_")

    def _merge_strings(self, *values: Any) -> list[str]:
        merged: list[str] = []
        for value in values:
            if isinstance(value, str):
                items = [value]
            elif isinstance(value, list):
                items = value
            else:
                items = []
            for item in items:
                text = self._normalize_path(str(item))
                if text and text not in merged:
                    merged.append(text)
        return merged

    def _append_violation(self, violations: list[str], code: str) -> None:
        if code not in violations:
            violations.append(code)
