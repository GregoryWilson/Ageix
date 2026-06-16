from __future__ import annotations

from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {
    ".py",
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
}

IGNORED_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "venv",
    ".venv",
    "artifacts",
}

AGEIX_RUNTIME_DIRS = {
    "logs",
    "manifests",
    "staged",
    "staging",
    "runs",
    "verification",
    "runtime",
    "repair_loops",
    "user_feedback",
}

AGEIX_SOURCE_DIRS = {
    "config",
    "projects",
    "objectives",
}

SOURCE_ROOT_SCORES = {
    "agents": 100,
    "services": 100,
    "models": 90,
    "tests": 90,
    "prompts": 70,
    "schemas": 70,
    "core": 60,
    "contracts": 60,
    "llm": 50,
    "providers": 50,
    "safety": 40,
    "tools": 40,
    "utils": 40,
    ".ageix": 20,
}

PATTERN_BONUSES = {
    "_service.py": 30,
    "_agent.py": 30,
    "worker": 20,
    "test_": 20,
    "schema": 10,
    "model": 10,
}

DEFAULT_EVIDENCE_LIMIT = 12


class RepositoryEvidenceService:
    """Filters and scores repository files for compact implementation evidence."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()

    def list_source_files(self) -> list[str]:
        files: list[str] = []
        for path in self.repo_root.rglob("*"):
            if not path.is_file():
                continue
            rel = self._relative_text(path)
            if not rel:
                continue
            if self.is_ignored_path(rel):
                continue
            files.append(rel)
        return sorted(files)

    def is_ignored_path(self, path_text: str) -> bool:
        path = self._normalize(path_text)
        parts = Path(path).parts
        if any(part in IGNORED_PARTS for part in parts):
            return True
        if len(parts) >= 2 and parts[0] == ".ageix":
            if parts[1] in AGEIX_RUNTIME_DIRS:
                return True
            if parts[1] not in AGEIX_SOURCE_DIRS:
                return True
        return False

    def select_evidence_files(
        self,
        *,
        objective: str = "",
        target_files: Iterable[str] | None = None,
        known_files: Iterable[str] | None = None,
        limit: int = DEFAULT_EVIDENCE_LIMIT,
    ) -> list[str]:
        target_list = [self._normalize(path) for path in (target_files or [])]
        target_set = set(target_list)
        candidates = [
            self._normalize(path)
            for path in (known_files or self.list_source_files())
        ]
        candidates = [
            path
            for path in candidates
            if path and path not in target_set and not self.is_ignored_path(path)
        ]

        selected: list[str] = []
        selected.extend(self._pattern_examples(candidates, target_list))
        selected.extend(self._ranked_files(candidates, objective, target_list, limit=limit))

        compact: list[str] = []
        for path in selected:
            if path not in compact:
                compact.append(path)
            if len(compact) >= limit:
                break
        return compact

    def score_file(self, path_text: str, *, objective: str = "", target_files: Iterable[str] | None = None) -> int:
        path = self._normalize(path_text)
        if not path or self.is_ignored_path(path):
            return -10_000

        parts = Path(path).parts
        name = Path(path).name
        score = SOURCE_ROOT_SCORES.get(parts[0], 0) if parts else 0

        for pattern, bonus in PATTERN_BONUSES.items():
            if pattern in name or pattern in path:
                score += bonus

        objective_tokens = self._tokens(objective)
        path_tokens = self._tokens(path)
        score += 10 * len(objective_tokens & path_tokens)

        for target in target_files or []:
            target_tokens = self._tokens(target)
            score += 8 * len(path_tokens & target_tokens)

        # Prefer source-like files over metadata/config once source matches exist.
        if Path(path).suffix == ".py":
            score += 10

        return score

    def _pattern_examples(self, candidates: list[str], target_files: list[str]) -> list[str]:
        examples: list[str] = []
        if any(path.startswith("services/") for path in target_files):
            examples.extend(self._best(candidates, lambda path: path.startswith("services/") and path.endswith("_service.py"), target_files, 2))
        if any(path.startswith("agents/") or "worker" in Path(path).name for path in target_files):
            examples.extend(self._best(candidates, lambda path: path.startswith("agents/") and ("worker" in Path(path).name or path.endswith("_agent.py")), target_files, 2))
        if any(path.startswith("models/") for path in target_files):
            examples.extend(self._best(candidates, lambda path: path.startswith("models/") and path.endswith(".py"), target_files, 2))
        if any(path.startswith("tests/") or Path(path).name.startswith("test_") for path in target_files):
            examples.extend(self._best(candidates, lambda path: path.startswith("tests/test_") and path.endswith(".py"), target_files, 2))
        return examples

    def _best(self, candidates: list[str], predicate, target_files: list[str], limit: int) -> list[str]:
        matches = [path for path in candidates if predicate(path)]
        return sorted(
            matches,
            key=lambda path: (-self.score_file(path, target_files=target_files), path),
        )[:limit]

    def _ranked_files(self, candidates: list[str], objective: str, target_files: list[str], limit: int) -> list[str]:
        ranked = sorted(
            candidates,
            key=lambda path: (-self.score_file(path, objective=objective, target_files=target_files), path),
        )
        return ranked[:limit]

    def _relative_text(self, path: Path) -> str | None:
        try:
            return self._normalize(str(path.resolve().relative_to(self.repo_root)))
        except ValueError:
            return None

    def _normalize(self, path_text: str) -> str:
        normalized = str(path_text).replace("\\", "/").strip()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized

    def _tokens(self, text: str) -> set[str]:
        token = ""
        tokens: set[str] = set()
        for char in text.lower():
            if char.isalnum():
                token += char
            else:
                if len(token) >= 3:
                    tokens.add(token)
                token = ""
        if len(token) >= 3:
            tokens.add(token)
        return tokens
