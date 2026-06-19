from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from models.auth_identity import AuthIdentity
from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.capability_registry_service import CapabilityRegistryService
from services.mcp_context import AgeixEnvelope, AgeixRequestContext
from web.auth import get_auth_identity, validate_request_context
from web.dependencies import get_repo_root

router = APIRouter()


class CapabilityExecutePayload(BaseModel):
    context: AgeixRequestContext
    capability_id: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/capabilities")
def list_capabilities(identity: AuthIdentity = Depends(get_auth_identity), repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    capabilities = [item.model_dump() for item in CapabilityRegistryService(repo_root).list_capabilities()]
    return AgeixEnvelope.ok({"capabilities": capabilities}, auth={"enabled": identity.auth_enabled, "client_id": identity.client_id if identity.auth_enabled else None}).model_dump()


@router.post("/capabilities/execute")
def execute_capability(payload: CapabilityExecutePayload, identity: AuthIdentity = Depends(get_auth_identity), repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    validate_request_context(identity, payload.context, repo_root)
    response = CapabilityExecutionService(repo_root).execute(CapabilityRequest(
        capability_id=payload.capability_id,
        session_id=payload.context.session_id,
        agent_id=payload.context.agent_id,
        arguments={
            **payload.arguments,
            "project_id": payload.context.project_id,
            "client_id": payload.context.client_id,
            **({"participant_id": payload.context.participant_id} if payload.context.participant_id else {}),
        },
    ))
    return AgeixEnvelope(
        success=response.success,
        result=response.result,
        errors=[response.error] if response.error else [],
        governance={"capability_id": payload.capability_id, "chair_authority_preserved": True},
        metadata={**response.metadata, "authenticated_client_id": identity.client_id if identity.auth_enabled else None},
    ).model_dump()
