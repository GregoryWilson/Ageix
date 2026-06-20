from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class EscalationDecisionAction(str, Enum):
    LOCAL_ONLY = "local_only"
    CONSULTATION_REQUIRED = "consultation_required"
    REPAIR_REQUIRED = "repair_required"
    HUMAN_REQUIRED = "human_required"


class ConsultationType(str, Enum):
    ARCHITECTURE_REVIEW = "architecture_review"
    PLANNING_ANALYSIS = "planning_analysis"
    VALIDATION_REVIEW = "validation_review"
    REPAIR_ANALYSIS = "repair_analysis"
    IMPLEMENTATION_ADVISORY = "implementation_advisory"


class EscalationDecision(BaseModel):
    action: EscalationDecisionAction
    reasons: list[str] = Field(default_factory=list)
    consultation_type: ConsultationType | None = None
    human_guidance_allowed: bool = True


class TokenEstimate(BaseModel):
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_total_tokens: int = 0
    cached_prefix_tokens: int = 0
    fresh_input_tokens: int = 0
    estimation_method: str = "chars_div_4"


class CostEstimate(BaseModel):
    model: str
    estimated_input_cost: float = 0.0
    estimated_output_cost: float = 0.0
    estimated_total_cost: float = 0.0
    currency: str = "USD"


class EvidenceDictionaryItem(BaseModel):
    evidence_id: str
    evidence_type: Literal[
        "approved_scope",
        "code_slice",
        "repository_summary",
        "dependency_summary",
        "impact_summary",
        "acceptance_criteria",
        "test_targets",
    ]
    summary: str
    type: str | None = None
    estimated_tokens: int = 0
    paths: list[str] = Field(default_factory=list)
    requestable: bool = True
    reference_only: bool = False
    payload: Any | None = None

    @model_validator(mode="after")
    def populate_type_alias(self) -> "EvidenceDictionaryItem":
        if self.type is None:
            self.type = self.evidence_type
        return self


class EvidenceDictionary(BaseModel):
    objective: str = ""
    items: list[EvidenceDictionaryItem] = Field(default_factory=list)
    excluded_reasons: list[str] = Field(default_factory=list)
    estimated_total_tokens: int = 0


class ConsultationProposal(BaseModel):
    consultation_type: ConsultationType
    target_model: str
    reason_for_consultation: list[str] = Field(default_factory=list)
    expected_benefit: list[str] = Field(default_factory=list)
    impact_if_skipped: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=lambda: [
        "approve_cloud_consultation",
        "provide_human_guidance",
        "continue_local_only",
        "abort",
    ])
    requires_human_approval: bool = True
    human_guidance_allowed: bool = True
    approved_scope_summary: list[str] = Field(default_factory=list)
    token_estimate: TokenEstimate = Field(default_factory=TokenEstimate)
    cost_estimate: CostEstimate | None = None
    evidence_dictionary: EvidenceDictionary | None = None
    governance: dict[str, Any] = Field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()
