from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field
from models.discovery import DiscoveryConfidence, DiscoveryResult
from models.research import ResearchResult
from models.architecture_review import ArchitectureReview


class BlockerLineage(BaseModel):
    blocker_id: str
    blocker_code: str
    resolver: str
    resolved: bool = False
    resolved_by: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class DiscoveryResolutionResult(BaseModel):
    status: Literal[
        "discovery_required",
        "research_pending",
        "architecture_pending",
        "ready_for_planning",
    ]
    discovery: DiscoveryResult
    research_results: list[ResearchResult] = Field(default_factory=list)
    architecture_review: ArchitectureReview | None = None
    confidence: DiscoveryConfidence
    blocker_lineage: list[BlockerLineage] = Field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == "ready_for_planning"
