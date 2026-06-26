from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError, BaseModel, ConfigDict, Field

from models.auth_identity import AuthIdentity
from services.mcp_context import AgeixExternalRequestContext
from services.mcp_service import MCPService
from web.auth import get_auth_identity, resolve_request_context
from web.dependencies import get_repo_root

router = APIRouter()


def _external_context(session_id: str, project_id: str) -> AgeixExternalRequestContext:
    try:
        return AgeixExternalRequestContext(session_id=session_id, project_id=project_id)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class ProposalCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context: AgeixExternalRequestContext
    objective: str = Field(min_length=1)
    proposal_type: str = "investigation"
    arguments: dict[str, Any] = Field(default_factory=dict)


class ContextQueryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context: AgeixExternalRequestContext
    limit: int = 50


@router.post("/proposals")
def create_proposal(payload: ProposalCreatePayload, identity: AuthIdentity = Depends(get_auth_identity), repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    context = resolve_request_context(identity, payload.context, repo_root)
    args = {**payload.arguments, "objective": payload.objective, "proposal_type": payload.proposal_type}
    return MCPService(repo_root).execute_capability("proposal.submit", context, args).model_dump()


@router.get("/proposals/{proposal_id}")
def get_proposal(
    proposal_id: str,
    session_id: str,
    project_id: str,
    identity: AuthIdentity = Depends(get_auth_identity),
    repo_root: Path = Depends(get_repo_root),
) -> dict[str, Any]:
    context = resolve_request_context(identity, _external_context(session_id, project_id), repo_root)
    return MCPService(repo_root).execute_capability("proposal.details", context, {"proposal_id": proposal_id}).model_dump()


@router.get("/proposals")
def list_proposals(
    session_id: str,
    project_id: str,
    limit: int = 50,
    identity: AuthIdentity = Depends(get_auth_identity),
    repo_root: Path = Depends(get_repo_root),
) -> dict[str, Any]:
    context = resolve_request_context(identity, _external_context(session_id, project_id), repo_root)
    return MCPService(repo_root).execute_capability("proposal.list", context, {"limit": limit}).model_dump()
