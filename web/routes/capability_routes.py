from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService
from services.capability_registry_service import CapabilityRegistryService
from services.mcp_context import AgeixEnvelope, AgeixRequestContext
from web.dependencies import get_repo_root

router = APIRouter()


class CapabilityExecutePayload(BaseModel):
    context: AgeixRequestContext
    capability_id: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/capabilities")
def list_capabilities(repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    capabilities = [item.model_dump() for item in CapabilityRegistryService(repo_root).list_capabilities()]
    return AgeixEnvelope.ok({"capabilities": capabilities}).model_dump()


@router.post("/capabilities/execute")
def execute_capability(payload: CapabilityExecutePayload, repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    if payload.capability_id in {"repository.raw_write", "worker.direct_execute", "promotion.direct_execute"}:
        # Authenticated callers get explicit governed denials; unauth/security is reserved for 14.1 auth.
        pass
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
        metadata=response.metadata,
    ).model_dump()
