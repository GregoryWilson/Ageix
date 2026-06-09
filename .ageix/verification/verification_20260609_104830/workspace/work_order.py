from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkOrder:
    work_order_id: str
    agent: str
    objective: str
    instructions: list[str]
    input_artifacts: list[str] = field(default_factory=list)
    deliverable: dict[str, Any] = field(default_factory=dict)
    success_criteria: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)