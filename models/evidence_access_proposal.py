from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


EvidenceRequestType = Literal["file", "section", "symbol", "line_range", "directory_summary"]


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


class EvidenceAccessProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: f"EAP-{uuid4().hex[:12].upper()}")
    session_id: str
    agent_id: str
    project_id: str
    objective: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    requested_evidence: list[EvidenceRequestItem] = Field(default_factory=list)
    human_approval: dict[str, Any] | None = None


class EvidenceAccessDecision(BaseModel):
    proposal_id: str
    decision: Literal["approved", "denied", "human_approval_required"]
    approved_evidence: list[dict[str, Any]] = Field(default_factory=list)
    denied_evidence: list[dict[str, Any]] = Field(default_factory=list)
    human_approval_required: bool = False
    reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
