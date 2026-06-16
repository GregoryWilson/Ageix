from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkPacket(BaseModel):
    """Planner-owned implementation contract for DevWorker execution."""

    objective: str
    implementation_strategy: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    repository_evidence: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    test_targets: list[str] = Field(default_factory=list)
    test_commands: list[str] = Field(default_factory=list)
    architecture_constraints: list[str] = Field(default_factory=list)
    discovery_evidence: dict[str, Any] = Field(default_factory=dict)
    impacted_files: list[str] = Field(default_factory=list)
    impacted_tests: list[str] = Field(default_factory=list)
    companion_files: list[str] = Field(default_factory=list)
    impact_summary: dict[str, Any] = Field(default_factory=dict)
    approved_target_files: list[str] = Field(default_factory=list)
    approved_companion_tests: list[str] = Field(default_factory=list)
    approved_scope: list[str] = Field(default_factory=list)
    context_selection_evidence: dict[str, Any] = Field(default_factory=dict)
