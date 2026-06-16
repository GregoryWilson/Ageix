from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


WorkerName = Literal["planner", "devworker", "validation", "cloud"]


class EvidenceSelectionEvidence(BaseModel):
    """Explainable audit record for worker context selection."""

    worker: str
    selected_files: list[str] = Field(default_factory=list)
    excluded_files: list[str] = Field(default_factory=list)
    selected_chars: int = 0
    excluded_chars: int = 0
    selection_reason: str = ""
    budget_applied: bool = False
    overflow_policy: str = "summarize"


class WorkerContextPackage(BaseModel):
    """Role-scoped context supplied to one Ageix worker."""

    worker: str
    objective: str = ""
    summary: str = ""
    files: dict[str, str] = Field(default_factory=dict)
    repository_summaries: list[str] = Field(default_factory=list)
    impact_summary: dict[str, Any] = Field(default_factory=dict)
    dependency_summary: dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: list[str] = Field(default_factory=list)
    test_targets: list[str] = Field(default_factory=list)
    approved_scope: list[str] = Field(default_factory=list)
    raw_graphs_included: bool = False
    full_repository_inventory_included: bool = False
    selection_evidence: EvidenceSelectionEvidence
