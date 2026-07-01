from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ExecutionWarningSeverity = Literal["info", "warning", "error"]


class ExecutionWarning(BaseModel):
    """A small structured warning emitted during governed DevWorker execution.

    Used instead of raw string-only warnings so that missing, skipped, partial,
    or degraded conditions are captured in an audit-friendly, machine-readable
    form. Warnings never change authority or lifecycle state; they are surfaced
    through DevJob result metadata and append-only DevJob events.
    """

    code: str = Field(min_length=1)
    severity: ExecutionWarningSeverity = "warning"
    message: str = Field(min_length=1)
    related_object_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
