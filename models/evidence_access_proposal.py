from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


EvidenceRequestType = Literal["file", "section", "symbol", "line_range", "directory_summary"]
EvidenceRequestMode = Literal["explicit", "intent"]
EvidenceIntentType = Literal["debugging", "feature_design", "architecture_review", "refactor", "validation", "documentation", "unknown"]
EvidencePlanDecision = Literal["approved", "denied", "human_approval_required"]



class EvidenceRequestItem(BaseModel):
    type: EvidenceRequestType
    path: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    symbol: str | None = None
    start_line: int | None = None
    end_line: int | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "EvidenceRequestItem":
        if self.type == "symbol" and not self.symbol:
            raise ValueError("symbol evidence requests require symbol")
        if self.type == "section" and not self.symbol and (self.start_line is None or self.end_line is None):
            raise ValueError("section evidence requests require either symbol or start_line/end_line")
        if self.type in {"line_range", "section"} and (self.start_line is not None or self.end_line is not None):
            if self.start_line is None or self.end_line is None:
                raise ValueError(f"{self.type} line evidence requests require both start_line and end_line")
            if self.start_line < 1 or self.end_line < self.start_line:
                raise ValueError(f"{self.type} line ranges must use positive ordered line numbers")
        return self


class EvidencePlanTarget(BaseModel):
    target_type: str = Field(min_length=1)
    target: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class EvidencePlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: f"EVP-{uuid4().hex[:12].upper()}")
    proposal_id: str
    request_mode: Literal["intent"] = "intent"
    intent_type: EvidenceIntentType = "unknown"
    objective: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    target: str = Field(min_length=1)
    desired_outcome: str = Field(min_length=1)
    resolved_targets: list[EvidencePlanTarget] = Field(default_factory=list)
    evidence_needed: list[str] = Field(default_factory=list)
    planning_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_reason: str = ""
    coverage_gaps: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    expires_at: str | None = None


class EvidenceAccessProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: f"EAP-{uuid4().hex[:12].upper()}")
    session_id: str
    agent_id: str
    project_id: str
    objective: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    request_mode: EvidenceRequestMode = "explicit"
    requested_evidence: list[EvidenceRequestItem] = Field(default_factory=list)
    target: str | None = None
    desired_outcome: str | None = None
    intent_type: EvidenceIntentType = "unknown"
    human_approval: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_request_mode(self) -> "EvidenceAccessProposal":
        if self.request_mode == "explicit" and not self.requested_evidence:
            # Existing service-level error message is preserved for backwards compatibility.
            return self
        if self.request_mode == "intent":
            if not self.target or not self.target.strip():
                raise ValueError("intent evidence requests require target")
            if not self.desired_outcome or not self.desired_outcome.strip():
                raise ValueError("intent evidence requests require desired_outcome")
        return self


class EvidenceAccessDecision(BaseModel):
    proposal_id: str
    decision: Literal["approved", "denied", "human_approval_required"]
    approved_evidence: list[dict[str, Any]] = Field(default_factory=list)
    denied_evidence: list[dict[str, Any]] = Field(default_factory=list)
    human_approval_required: bool = False
    reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence_plan: EvidencePlan | None = None
