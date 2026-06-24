from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ArchitectureWorkContextPackage(BaseModel):
    """Immutable summary-first architecture work analysis context snapshot."""

    work_context_id: str = Field(default_factory=lambda: f"WORKCTX-{uuid4().hex[:12].upper()}")
    project_id: str = Field(min_length=1)
    scope: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str = "architecture_work_context_service"

    work_summary: str = ""
    affected_scope: dict[str, Any] = Field(default_factory=dict)
    resolved_scope: dict[str, Any] = Field(default_factory=dict)
    resolved_architecture_nodes: list[dict[str, Any]] = Field(default_factory=list)
    guidance_context: dict[str, Any] = Field(default_factory=dict)
    guidance_context_package_ids: list[str] = Field(default_factory=list)
    governing_principles: list[dict[str, Any]] = Field(default_factory=list)
    active_intent: list[dict[str, Any]] = Field(default_factory=list)
    related_adrs: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    future_direction: list[dict[str, Any]] = Field(default_factory=list)
    open_considerations: list[dict[str, Any]] = Field(default_factory=list)
    impacted_nodes: list[dict[str, Any]] = Field(default_factory=list)
    relationship_summary: dict[str, Any] = Field(default_factory=dict)
    revision_context: list[dict[str, Any]] = Field(default_factory=list)
    governance_lineage: dict[str, Any] = Field(default_factory=dict)
    traceability: list[dict[str, Any]] = Field(default_factory=list)

    immutable_snapshot: bool = True
    summary_first: bool = True
    generated_on_demand: bool = True
    persisted_snapshot: bool = False
    impact_max_depth: int = 1
    deterministic_scope_resolution: bool = True
    detail_available: bool = True
    detail_path: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
