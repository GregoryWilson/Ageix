from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RepairDecisionAction(str, Enum):
    APPROVE_REPAIR = "approve_repair"
    STOP_REPAIR = "stop_repair"
    REQUEST_HUMAN_REVIEW = "request_human_review"


@dataclass(frozen=True)
class RepairDecision:
    action: RepairDecisionAction
    reasoning: str