from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from services.repository_evidence_service import RepositoryEvidenceService


@dataclass(frozen=True)
class RepositoryInventory:
    """Authoritative local repository inventory for deterministic grounding."""

    files: list[str] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)

    @property
    def paths(self) -> list[str]:
        return sorted(dict.fromkeys(self.files + self.directories))

    def contains(self, path: str) -> bool:
        normalized = path.replace("\\", "/").strip().lstrip("./")
        return normalized in set(self.paths)


class RepositoryInventoryService:
    """Builds and caches the authoritative repository inventory."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self._inventory: RepositoryInventory | None = None
        self._evidence_service = RepositoryEvidenceService(self.repo_root)

    def inventory(self, *, refresh: bool = False) -> RepositoryInventory:
        if self._inventory is None or refresh:
            self._inventory = RepositoryInventory(
                files=self._list_files(),
                directories=self._list_directories(),
            )
        return self._inventory

    def _list_files(self) -> list[str]:
        return self._evidence_service.list_source_files()

    def _list_directories(self) -> list[str]:
        directories: set[str] = set()
        for file_path in self._list_files():
            parent = Path(file_path).parent
            while str(parent) not in {".", ""}:
                normalized = str(parent).replace("\\", "/")
                if not self._evidence_service.is_ignored_path(normalized):
                    directories.add(normalized)
                parent = parent.parent
        return sorted(directories)
