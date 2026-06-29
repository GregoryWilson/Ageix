from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.auth_identity import AuthIdentity
from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.capability_registry_service import CapabilityRegistryService
from services.mcp_context import AgeixEnvelope, AgeixExternalRequestContext
from web.auth import get_auth_identity, resolve_request_context, safe_request_headers
from web.dependencies import get_repo_root

router = APIRouter()


class CapabilityExecutePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: AgeixExternalRequestContext
    capability_id: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_identity_fields(self) -> "CapabilityExecutePayload":
        forbidden_top_level = {"client_id", "agent_id", "trust_profile", "authorization_context", "authentication_method"}
        forbidden_arguments = forbidden_top_level.intersection(set((self.arguments or {}).keys()))
        if forbidden_arguments:
            raise ValueError(f"identity_fields_not_allowed:{','.join(sorted(forbidden_arguments))}")
        return self


@router.get("/capabilities")
def list_capabilities(identity: AuthIdentity = Depends(get_auth_identity), repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    capabilities = [item.model_dump() for item in CapabilityRegistryService(repo_root).list_capabilities()]
    return AgeixEnvelope.ok({"capabilities": capabilities}, auth={"enabled": identity.auth_enabled, "client_id": identity.client_id if identity.auth_enabled else None}).model_dump()


@router.post("/capabilities/execute")
def execute_capability(
    payload: CapabilityExecutePayload,
    request: Request,
    identity: AuthIdentity = Depends(get_auth_identity),
    repo_root: Path = Depends(get_repo_root),
) -> dict[str, Any]:
    context = resolve_request_context(
        identity,
        payload.context,
        repo_root,
        client_user_agent=request.headers.get("user-agent"),
        client_headers=safe_request_headers(request),
    )
    if not identity.capability_allowed(payload.capability_id):
        return AgeixEnvelope.denied("capability_not_authorized_for_token", capability_id=payload.capability_id).model_dump()
    response = CapabilityExecutionService(repo_root).execute(CapabilityRequest(
        capability_id=payload.capability_id,
        session_id=context.session_id,
        agent_id=context.agent_id,
        arguments={
            **payload.arguments,
            "project_id": context.project_id,
            "client_id": context.client_id,
            "client_context": {
                "client_id": context.client_id,
                "agent_id": context.agent_id,
                "provider": context.provider,
                "session_id": context.session_id,
                "project_id": context.project_id,
                "participant_id": context.participant_id,
                "authority_granted": False,
            },
            **({"participant_id": context.participant_id} if context.participant_id else {}),
            **({"client_user_agent": context.client_user_agent} if context.client_user_agent else {}),
            "authentication_method": identity.authentication_method,
        },
    ))
    return AgeixEnvelope(
        success=response.success,
        result=response.result,
        errors=[response.error] if response.error else [],
        governance={"capability_id": payload.capability_id, "chair_authority_preserved": True},
        metadata={**response.metadata, "authenticated_client_id": identity.client_id if identity.auth_enabled else None, "authenticated_agent_id": identity.agent_id if identity.auth_enabled else None},
    ).model_dump()
