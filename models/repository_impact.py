from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class RepositoryImpactRelationship(str, Enum):
    DIRECT_DEPENDENT = "direct_dependent"
    INDIRECT_DEPENDENT = "indirect_dependent"
    IMPACTED_TEST = "impacted_test"
    COMPANION_TEST = "companion_test"
    SIBLING_MODULE = "sibling_module"
    UNRELATED = "unrelated"


class RepositoryImpactEvidence(BaseModel):
    source_file: str
    impacted_file: str
    relationship: RepositoryImpactRelationship
    depth: int
    reason: str
    confidence: float = 0.0


class RepositoryImpactResult(BaseModel):
    status: Literal["pass", "warn", "disabled"] = "pass"
    impact_graph: dict[str, list[str]] = Field(default_factory=dict)
    impacted_files: list[str] = Field(default_factory=list)
    impacted_tests: list[str] = Field(default_factory=list)
    companion_files: list[str] = Field(default_factory=list)
    evidence: list[RepositoryImpactEvidence] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    violations: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status in {"pass", "warn", "disabled"}
