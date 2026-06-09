# core/worker_result.py

from typing import Any, Literal
from pydantic import BaseModel, Field


WorkerStatus = Literal["completed", "failed", "needs_input"]


class CommandResult(BaseModel):
    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""


class WorkerResult(BaseModel):
    status: WorkerStatus
    summary: str
    changed_files: list[str] = Field(default_factory=list)
    patch: str | None = None
    commands_run: list[CommandResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    next_recommendation: str | None = None
    deliverable: dict[str, Any] = Field(default_factory=dict)