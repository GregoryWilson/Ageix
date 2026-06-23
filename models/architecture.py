from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ArchitectureNodeType(str, Enum):
    PROJECT = "project"
    DOMAIN = "domain"
    COMPONENT = "component"


class ArchitectureNodeStatus(str, Enum):
    ACTIVE = "active"
    PLANNED = "planned"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class ArchitectureDescriptionState(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"


class ArchitectureReviewTransportMode(str, Enum):
    MCP_CONTEXTUAL = "mcp_contextual"
    API_PACKET = "api_packet"
    DISABLED = "disabled"


class ArchitectureMetadataCompleteness(BaseModel):
    name: bool = False
    description: bool = False
    node_key: bool = False
    path: bool = False
    parent: bool = False


class ArchitectureHealth(BaseModel):
    status: str = "unknown"
    linked_evidence_count: int = 0
    linked_decision_count: int = 0
    metadata_completeness: ArchitectureMetadataCompleteness = Field(default_factory=ArchitectureMetadataCompleteness)


class ArchitectureReviewerDefinition(BaseModel):
    reviewer_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    role: str = Field(default="cloud_architect")
    enabled: bool = False
    transport_mode: ArchitectureReviewTransportMode = ArchitectureReviewTransportMode.DISABLED
    can_submit_review: bool = True
    can_propose_revision: bool = True
    can_directly_modify_architecture: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArchitectureNode(BaseModel):
    architecture_id: str = Field(default_factory=lambda: f"ARCH-{uuid4().hex[:12].upper()}")
    project_id: str = Field(min_length=1)
    node_key: str = Field(min_length=1)
    path: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    parent_id: str | None = None
    node_type: ArchitectureNodeType
    status: ArchitectureNodeStatus = ArchitectureNodeStatus.ACTIVE
    linked_evidence_package_ids: list[str] = Field(default_factory=list)
    linked_decision_trace_ids: list[str] = Field(default_factory=list)
    description_state: ArchitectureDescriptionState = ArchitectureDescriptionState.DRAFT
    metadata: dict[str, Any] = Field(default_factory=dict)
    health: ArchitectureHealth = Field(default_factory=ArchitectureHealth)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ArchitectureDescription(BaseModel):
    description_id: str = Field(default_factory=lambda: f"ARCHDESC-{uuid4().hex[:12].upper()}")
    architecture_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    version: int = 1
    state: ArchitectureDescriptionState = ArchitectureDescriptionState.DRAFT
    source_actor: str = "architect_worker"
    reviewed_by: str | None = None
    approved_by: str | None = None
    purpose: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    detailed_description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ArchitectureContext(BaseModel):
    architecture_id: str
    project_id: str
    path: str
    node_type: ArchitectureNodeType
    name: str
    summary: str = ""
    purpose: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    parent_context: dict[str, Any] | None = None
    child_context: list[dict[str, Any]] = Field(default_factory=list)
    linked_evidence_summary: list[dict[str, Any]] = Field(default_factory=list)
    linked_decision_summary: list[dict[str, Any]] = Field(default_factory=list)
    description: dict[str, Any] | None = None
    detail_available: bool = False
    detail: dict[str, Any] = Field(default_factory=dict)
    context_policy: dict[str, Any] = Field(default_factory=dict)


class ArchitectureIndexEntry(BaseModel):
    architecture_id: str
    project_id: str
    node_key: str
    path: str
    name: str
    node_type: ArchitectureNodeType
    status: ArchitectureNodeStatus
    parent_id: str | None = None
    child_ids: list[str] = Field(default_factory=list)
    linked_evidence_count: int = 0
    linked_decision_count: int = 0
    description_state: ArchitectureDescriptionState = ArchitectureDescriptionState.DRAFT
    updated_at: str | None = None
