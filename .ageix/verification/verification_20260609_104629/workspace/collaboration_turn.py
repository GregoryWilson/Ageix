from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


Speaker = Literal["greg", "chatgpt", "ageix", "chair", "agent"]
Intent = Literal[
    "discussion",
    "instruction",
    "change_plan",
    "approved_execution",
    "question",
    "execution_result",
    "review",
    "blocker",
    "status",
]


class CollaborationTurn(BaseModel):
    conversation_id: str
    speaker: Speaker
    target: str | None = None
    intent: Intent = "discussion"
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CollaborationDecision(BaseModel):
    should_execute: bool = False
    target_agent: str | None = None
    objective: str = ""
    instructions: list[str] = Field(default_factory=list)
    reason: str = ""