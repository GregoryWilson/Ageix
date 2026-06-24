from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ArchitectureGuidanceContextPackage(BaseModel):
    """Immutable summary-first architecture guidance context snapshot."""

    package_id: str = Field(default_factory=lambda: f"GUIDECTX-{uuid4().hex[:12].upper()}")
    project_id: str = Field(min_length=1)
    architecture_id: str = Field(min_length=1)
    architecture_scope: dict[str, Any] = Field(default_factory=dict)
    affected_nodes: list[dict[str, Any]] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str = "architecture_guidance_context_service"

    source_revision_id: str | None = None
    active_revision_summary: dict[str, Any] | None = None
    revision_lineage: list[dict[str, Any]] = Field(default_factory=list)
    architecture_node_summary: dict[str, Any] = Field(default_factory=dict)

    brief_summary: str = ""
    governing_principles: list[dict[str, Any]] = Field(default_factory=list)
    active_intent: list[dict[str, Any]] = Field(default_factory=list)
    decision_context: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    future_direction: list[dict[str, Any]] = Field(default_factory=list)
    open_considerations: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    traceability: list[dict[str, Any]] = Field(default_factory=list)
    governance_lineage: dict[str, Any] = Field(default_factory=dict)

    immutable_snapshot: bool = True
    summary_first: bool = True
    generated_on_demand: bool = True
    persisted_snapshot: bool = False
    detail_available: bool = True
    detail_path: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
