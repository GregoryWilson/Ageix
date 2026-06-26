from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class DependencyClassification(str, Enum):
    STDLIB_DEPENDENCY = "stdlib_dependency"
    EXISTING_REPO_DEPENDENCY = "existing_repo_dependency"
    PROPOSED_REPO_DEPENDENCY = "proposed_repo_dependency"
    APPROVED_MANIFEST_DEPENDENCY = "approved_manifest_dependency"
    APPROVED_TEST_DEPENDENCY = "approved_test_dependency"
    UNKNOWN_EXTERNAL_DEPENDENCY = "unknown_external_dependency"
    BLOCKED_DEPENDENCY = "blocked_dependency"


class DependencyValidationOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    GRAPH_LIMIT_EXCEEDED = "graph_limit_exceeded"
    DEPTH_LIMIT_EXCEEDED = "depth_limit_exceeded"
    NODE_LIMIT_EXCEEDED = "node_limit_exceeded"
    IMPORT_LIMIT_EXCEEDED = "import_limit_exceeded"


class DependencyImport(BaseModel):
    source_file: str
    dependency: str
    root: str
    depth: int = 0


class DependencyGraphEdge(BaseModel):
    source_file: str
    import_name: str
    dependency: str
    classification: DependencyClassification
    resolved_path: str | None = None
    depth: int = 0


class DependencyValidationEvidence(BaseModel):
    dependency: str
    classification: DependencyClassification
    resolved_path: str | None = None
    depth: int
    source_file: str


class DependencyIntelligenceResult(BaseModel):
    status: Literal["pass", "fail"]
    outcome: DependencyValidationOutcome = DependencyValidationOutcome.PASS
    graph: list[DependencyGraphEdge] = Field(default_factory=list)
    evidence: list[DependencyValidationEvidence] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "pass"
