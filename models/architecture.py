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


class ArchitectureCoverageStatus(str, Enum):
    UNKNOWN = "unknown"
    PARTIAL = "partial"
    SUBSTANTIAL = "substantial"
    COMPLETE_CURRENT_STATE = "complete_current_state"


class ArchitectureDescriptionStatus(str, Enum):
    MISSING = "missing"
    PARTIAL = "partial"
    COMPLETE = "complete"


class ArchitectureEvidenceStatus(str, Enum):
    MISSING = "missing"
    PRESENT = "present"


class ArchitectureDecisionStatus(str, Enum):
    NONE = "none"
    PRESENT = "present"


class ArchitectureReviewStatus(str, Enum):
    NEVER_REVIEWED = "never_reviewed"
    REVIEWED = "reviewed"


class ArchitectureContextStatus(str, Enum):
    AVAILABLE = "available"
    FAILED = "failed"


class ArchitectureFreshnessStatus(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class ArchitectureRegistrationStatus(str, Enum):
    REGISTERED = "registered"
    UNREGISTERED = "unregistered"
    UNKNOWN = "unknown"


class ArchitectureMetadataCompleteness(BaseModel):
    name: bool = False
    description: bool = False
    node_key: bool = False
    path: bool = False
    parent: bool = False


class ArchitectureHealth(BaseModel):
    architecture_id: str = ""
    status: str = "unknown"
    hierarchy_status: str = "unknown"
    coverage_status: ArchitectureCoverageStatus = ArchitectureCoverageStatus.UNKNOWN
    description_status: ArchitectureDescriptionStatus = ArchitectureDescriptionStatus.MISSING
    evidence_status: ArchitectureEvidenceStatus = ArchitectureEvidenceStatus.MISSING
    decision_status: ArchitectureDecisionStatus = ArchitectureDecisionStatus.NONE
    review_status: ArchitectureReviewStatus = ArchitectureReviewStatus.NEVER_REVIEWED
    context_status: ArchitectureContextStatus = ArchitectureContextStatus.FAILED
    freshness_status: ArchitectureFreshnessStatus = ArchitectureFreshnessStatus.UNKNOWN
    registration_status: ArchitectureRegistrationStatus = ArchitectureRegistrationStatus.REGISTERED
    linked_evidence_count: int = 0
    linked_decision_count: int = 0
    review_count: int = 0
    health_version: int = 1
    metadata_completeness: ArchitectureMetadataCompleteness = Field(default_factory=ArchitectureMetadataCompleteness)
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_evaluated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


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
    created_by: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    last_reviewed_at: str | None = None
    review_count: int = 0
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


class ArchitectureCoverage(BaseModel):
    project_id: str
    coverage_status: ArchitectureCoverageStatus = ArchitectureCoverageStatus.UNKNOWN
    known_domains: int = 0
    mapped_domains: int = 0
    known_components: int = 0
    mapped_components: int = 0
    known_projects: int = 0
    mapped_projects: int = 0
    discovery_known_domains: int = 0
    discovery_known_components: int = 0
    discovery_status: ArchitectureRegistrationStatus = ArchitectureRegistrationStatus.UNKNOWN
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_evaluated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


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
