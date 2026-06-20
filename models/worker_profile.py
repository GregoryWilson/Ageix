from __future__ import annotations

from typing import Literal, Any
from pydantic import BaseModel, Field


class WorkerPersona(BaseModel):
    name: str
    principles: list[str] = Field(default_factory=list)
    tone: str = "direct"
    biases: list[str] = Field(default_factory=list)


class WorkerProfile(BaseModel):
    worker_id: str
    role: str
    persona: WorkerPersona
    capabilities: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    router_hints: dict[str, Any] = Field(default_factory=dict)
    authority: Literal["recommend_only", "block_planning"] = "recommend_only"
    prompt_file: str
    input_contract: str
    output_contract: str
