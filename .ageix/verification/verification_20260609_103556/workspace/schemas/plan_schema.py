from typing import Any

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    id: str
    agent: str

    objective: str
    instructions: str

    inputs: dict[str, Any] = Field(default_factory=dict)

    expected_output: dict[str, Any] = Field(default_factory=dict)

    constraints: dict[str, Any] = Field(default_factory=dict)

    success_criteria: list[str] = Field(default_factory=list)

    dependencies: list[str] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    objective: str
    strategy: str

    steps: list[PlanStep]

    metadata: dict[str, Any] = Field(default_factory=dict)