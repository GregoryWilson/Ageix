from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RepairAnalysis:
    patch_id: str
    verification_id: str
    observed_failure: str
    likely_cause: str
    relevant_evidence: list[str] = field(default_factory=list)
    recommended_repair_objective: str = ""