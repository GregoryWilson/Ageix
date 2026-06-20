from __future__ import annotations

import ast
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from models.dependency_intelligence import (
    DependencyClassification,
    DependencyGraphEdge,
    DependencyIntelligenceResult,
    DependencyValidationEvidence,
    DependencyValidationOutcome,
)
from services.controls_service import ControlsService


@dataclass(frozen=True)
class DependencyIntelligenceControls:
    enabled: bool = True
    max_depth: int = 2
    max_nodes: int = 50
    max_imports_per_file: int = 25
    follow_test_imports: bool = True
    follow_runtime_imports: bool = True
    allow_proposed_local_imports: bool = True
    allow_existing_local_imports: bool = True
    allow_stdlib_imports: bool = True
    allowed_test_dependencies: tuple[str, ...] = ("pytest",)
    blocked_dependencies: tuple[str, ...] = ()
    unknown_dependency_policy: str = "fail"

    @classmethod
    def from_raw(cls, raw: dict[str, Any] | None) -> "DependencyIntelligenceControls":
        raw = raw or {}
        return cls(
            enabled=bool(raw.get("enabled", True)),
            max_depth=int(raw.get("max_depth", 2)),
            max_nodes=int(raw.get("max_nodes", 50)),
            max_imports_per_file=int(raw.get("max_imports_per_file", 25)),
            follow_test_imports=bool(raw.get("follow_test_imports", True)),
            follow_runtime_imports=bool(raw.get("follow_runtime_imports", True)),
            allow_proposed_local_imports=bool(raw.get("allow_proposed_local_imports", True)),
            allow_existing_local_imports=bool(raw.get("allow_existing_local_imports", True)),
            allow_stdlib_imports=bool(raw.get("allow_stdlib_imports", True)),
            allowed_test_dependencies=tuple(str(x) for x in raw.get("allowed_test_dependencies", ["pytest"])),
            blocked_dependencies=tuple(str(x) for x in raw.get("blocked_dependencies", [])),
            unknown_dependency_policy=str(raw.get("unknown_dependency_policy", "fail")),
        )


class DependencyIntelligenceService:
    def __init__(self, repo_root: Path | str = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        raw = ControlsService(self.repo_root).get_raw_config().get("dependency_intelligence", {})
        self.controls = DependencyIntelligenceControls.from_raw(raw)

    def analyze(self, *, proposal: dict[str, Any], repository_state: dict[str, Any] | None = None) -> DependencyIntelligenceResult:
        del repository_state
        if not self.controls.enabled:
            return DependencyIntelligenceResult(status="pass")

        proposed_files = self._proposed_python_files(proposal)
        queue: list[tuple[str, str, int]] = [(path, content, 0) for path, content in proposed_files.items()]
        visited: set[str] = set()
        graph: list[DependencyGraphEdge] = []
        evidence: list[DependencyValidationEvidence] = []
        violations: list[str] = []

        while queue:
            source_file, content, depth = queue.pop(0)
            if source_file in visited:
                continue
            visited.add(source_file)
            if len(visited) > self.controls.max_nodes:
                return self._limit_result(DependencyValidationOutcome.NODE_LIMIT_EXCEEDED, graph, evidence, "node_limit_exceeded")
            if depth > self.controls.max_depth:
                return self._limit_result(DependencyValidationOutcome.DEPTH_LIMIT_EXCEEDED, graph, evidence, "depth_limit_exceeded")

            imports = self.parse_imports(content, source_file=source_file, depth=depth)
            if len(imports) > self.controls.max_imports_per_file:
                return self._limit_result(DependencyValidationOutcome.IMPORT_LIMIT_EXCEEDED, graph, evidence, "import_limit_exceeded")

            for import_name in imports:
                classification, resolved_path = self.classify_dependency(import_name, source_file, proposed_files)
                edge = DependencyGraphEdge(
                    source_file=source_file,
                    import_name=import_name,
                    dependency=import_name,
                    classification=classification,
                    resolved_path=resolved_path,
                    depth=depth + 1,
                )
                graph.append(edge)
                evidence.append(DependencyValidationEvidence(
                    dependency=import_name,
                    classification=classification,
                    resolved_path=resolved_path,
                    depth=depth + 1,
                    source_file=source_file,
                ))

                if classification in {DependencyClassification.UNKNOWN_EXTERNAL_DEPENDENCY, DependencyClassification.BLOCKED_DEPENDENCY}:
                    if classification != DependencyClassification.UNKNOWN_EXTERNAL_DEPENDENCY or self.controls.unknown_dependency_policy == "fail":
                        violations.append(f"{classification.value}: {import_name}")

                if classification in {DependencyClassification.EXISTING_REPO_DEPENDENCY, DependencyClassification.PROPOSED_REPO_DEPENDENCY}:
                    if self._should_follow(source_file) and resolved_path and depth + 1 <= self.controls.max_depth:
                        next_content = proposed_files.get(resolved_path) or self._read_file(resolved_path)
                        if next_content is not None:
                            queue.append((resolved_path, next_content, depth + 1))
                    elif depth + 1 > self.controls.max_depth:
                        return self._limit_result(DependencyValidationOutcome.DEPTH_LIMIT_EXCEEDED, graph, evidence, "depth_limit_exceeded")

        return DependencyIntelligenceResult(
            status="fail" if violations else "pass",
            outcome=DependencyValidationOutcome.FAIL if violations else DependencyValidationOutcome.PASS,
            graph=graph,
            evidence=evidence,
            violations=violations,
        )

    def parse_imports(self, content: str, *, source_file: str, depth: int = 0) -> list[str]:
        del source_file, depth
        imports: list[str] = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return self._parse_imports_from_text(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._append_unique(imports, alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                if node.module:
                    self._append_unique(imports, node.module)
        return imports

    def classify_dependency(self, import_name: str, source_file: str, proposed_files: dict[str, str] | None = None) -> tuple[DependencyClassification, str | None]:
        proposed_files = proposed_files or {}
        root = import_name.split(".")[0]
        normalized_root = self._normalize_dependency_name(root)

        if root in self.controls.blocked_dependencies or normalized_root in {self._normalize_dependency_name(x) for x in self.controls.blocked_dependencies}:
            return DependencyClassification.BLOCKED_DEPENDENCY, None
        if self._is_stdlib(root):
            return DependencyClassification.STDLIB_DEPENDENCY, None
        if self._is_test_path(source_file) and normalized_root in {self._normalize_dependency_name(x) for x in self.controls.allowed_test_dependencies}:
            return DependencyClassification.APPROVED_TEST_DEPENDENCY, None

        proposed_path = self._resolve_module(import_name, proposed_files=set(proposed_files))
        if proposed_path and self.controls.allow_proposed_local_imports:
            return DependencyClassification.PROPOSED_REPO_DEPENDENCY, proposed_path

        existing_path = self._resolve_module(import_name)
        if existing_path and self.controls.allow_existing_local_imports:
            return DependencyClassification.EXISTING_REPO_DEPENDENCY, existing_path

        if normalized_root in self._load_allowed_dependencies():
            return DependencyClassification.APPROVED_MANIFEST_DEPENDENCY, None
        return DependencyClassification.UNKNOWN_EXTERNAL_DEPENDENCY, None

    def _proposed_python_files(self, proposal: dict[str, Any]) -> dict[str, str]:
        files: dict[str, str] = {}
        for change in proposal.get("changes", []):
            path = change.get("path")
            content = change.get("content")
            if isinstance(path, str) and path.endswith(".py") and isinstance(content, str):
                files[path.replace("\\", "/")] = content
        return files

    def _resolve_module(self, import_name: str, proposed_files: set[str] | None = None) -> str | None:
        proposed_files = proposed_files or set()
        parts = import_name.split(".")
        candidates: list[str] = []
        for idx in range(len(parts), 0, -1):
            base = "/".join(parts[:idx])
            candidates.extend([f"{base}.py", f"{base}/__init__.py"])
        for candidate in candidates:
            if candidate in proposed_files:
                return candidate
        if proposed_files:
            return None
        for candidate in candidates:
            if (self.repo_root / candidate).exists():
                return candidate
        return None

    def _read_file(self, path: str) -> str | None:
        file_path = self.repo_root / path
        if not file_path.exists() or not file_path.is_file():
            return None
        return file_path.read_text(encoding="utf-8", errors="replace")

    def _should_follow(self, source_file: str) -> bool:
        return (self._is_test_path(source_file) and self.controls.follow_test_imports) or (not self._is_test_path(source_file) and self.controls.follow_runtime_imports)

    def _is_test_path(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        return normalized.startswith("tests/") or Path(normalized).name.startswith("test_")

    def _is_stdlib(self, root: str) -> bool:
        return self.controls.allow_stdlib_imports and (root in sys.builtin_module_names or root in getattr(sys, "stdlib_module_names", set()))

    def _parse_imports_from_text(self, content: str) -> list[str]:
        imports: list[str] = []
        patterns = [
            re.compile(r"^\s*import\s+([A-Za-z_][A-Za-z0-9_\.]*)", re.MULTILINE),
            re.compile(r"^\s*from\s+([A-Za-z_][A-Za-z0-9_\.]*)\s+import\s+", re.MULTILINE),
        ]
        for pattern in patterns:
            for match in pattern.finditer(content):
                self._append_unique(imports, match.group(1))
        return imports

    def _append_unique(self, values: list[str], value: str) -> None:
        if value not in values:
            values.append(value)

    def _limit_result(self, outcome: DependencyValidationOutcome, graph: list[DependencyGraphEdge], evidence: list[DependencyValidationEvidence], violation: str) -> DependencyIntelligenceResult:
        return DependencyIntelligenceResult(status="fail", outcome=outcome, graph=graph, evidence=evidence, violations=[violation])

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
        poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        if isinstance(poetry_deps, dict):
            raw_deps.extend(str(key) for key in poetry_deps if key.lower() != "python")
        deps: set[str] = set()
        for item in raw_deps:
            name = re.split(r"[<>=!~;\[]", item.strip(), maxsplit=1)[0].strip()
            if name:
                deps.add(self._normalize_dependency_name(name))
        return deps

    def _read_dependency_allowlist(self) -> set[str]:
        candidates = [self.repo_root / ".ageix" / "config" / "dependency_allowlist.txt", self.repo_root / ".ageix" / "dependency_allowlist.txt"]
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
