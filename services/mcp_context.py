from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class AgeixRequestContext(BaseModel):
    """Stable external-client context shared by HTTP and MCP boundaries."""

    client_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    participant_id: str | None = None

    @model_validator(mode="after")
    def reject_ambiguous_project(self) -> "AgeixRequestContext":
        if self.project_id.strip().lower() == "current":
            raise ValueError("project_id_must_be_explicit")
        return self


class AgeixEnvelope(BaseModel):
    """Standard response envelope for web/MCP service boundaries."""

    success: bool
    result: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    audit_id: str | None = None
    governance: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def ok(cls, result: dict[str, Any] | None = None, **metadata: Any) -> "AgeixEnvelope":
        return cls(success=True, result=result or {}, metadata=metadata)

    @classmethod
    def denied(cls, reason: str, *, security_violation: bool = False, **metadata: Any) -> "AgeixEnvelope":
        return cls(
            success=False,
            result={},
            errors=[reason],
            governance={"denied": True, "reason": reason, "security_violation": security_violation},
            metadata=metadata,
        )
