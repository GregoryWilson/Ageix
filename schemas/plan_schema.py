from typing import Any

from pydantic import BaseModel, Field

from models.work_packet import WorkPacket


class PlanStep(BaseModel):
    id: str
    agent: str

    objective: str
    instructions: str

    target_files: list[str] = Field(default_factory=list)

    inputs: dict[str, Any] = Field(default_factory=dict)

    expected_output: dict[str, Any] = Field(default_factory=dict)

    constraints: dict[str, Any] = Field(default_factory=dict)

    success_criteria: list[str] = Field(default_factory=list)

    dependencies: list[str] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    objective: str
    strategy: str

    steps: list[PlanStep]

    work_packet: WorkPacket | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)