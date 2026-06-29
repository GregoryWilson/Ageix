from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgeixExternalRequestContext(BaseModel):
    """External request context accepted from web clients.

    Identity fields are intentionally forbidden. client_id/agent_id/authentication
    data come from the authenticated credential, not the caller payload.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def reject_ambiguous_project(self) -> "AgeixExternalRequestContext":
        if self.project_id.strip().lower() == "current":
            raise ValueError("project_id_must_be_explicit")
        return self


class AgeixRequestContext(BaseModel):
    """Resolved transport-independent context shared by HTTP and MCP boundaries.

    This model is constructed by Ageix after authentication. It may still be used
    by internal MCP tests/tools, but web payloads should use AgeixExternalRequestContext.
    """

    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    participant_id: str | None = None
    provider: str | None = None
    display_name: str | None = None
    claimed_primary: bool | None = None
    authentication_method: str | None = None
    client_user_agent: str | None = None
    client_headers: dict[str, str] | None = None

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
            governance={"denied": True, "decision": "denied", "reason": reason, "security_violation": security_violation, "chair_authority_preserved": True},
            metadata=metadata,
        )
