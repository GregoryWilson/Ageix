from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from models.auth_identity import AuthIdentity
from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService
from web.auth import get_auth_identity, validate_request_context
from web.dependencies import get_repo_root

router = APIRouter()


class ProposalCreatePayload(BaseModel):
    context: AgeixRequestContext
    objective: str = Field(min_length=1)
    proposal_type: str = "investigation"
    arguments: dict[str, Any] = Field(default_factory=dict)


class ContextQueryPayload(BaseModel):
    context: AgeixRequestContext
    limit: int = 50


@router.post("/proposals")
def create_proposal(payload: ProposalCreatePayload, identity: AuthIdentity = Depends(get_auth_identity), repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    validate_request_context(identity, payload.context, repo_root)
    args = {**payload.arguments, "objective": payload.objective, "proposal_type": payload.proposal_type}
    return MCPService(repo_root).execute_capability("proposal.submit", payload.context, args).model_dump()


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str, client_id: str, agent_id: str, session_id: str, project_id: str, participant_id: str | None = None, identity: AuthIdentity = Depends(get_auth_identity), repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    context = AgeixRequestContext(client_id=client_id, agent_id=agent_id, session_id=session_id, project_id=project_id, participant_id=participant_id)
    validate_request_context(identity, context, repo_root)
    return MCPService(repo_root).execute_capability("proposal.details", context, {"proposal_id": proposal_id}).model_dump()


@router.get("/proposals")
def list_proposals(client_id: str, agent_id: str, session_id: str, project_id: str, limit: int = 50, participant_id: str | None = None, identity: AuthIdentity = Depends(get_auth_identity), repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    context = AgeixRequestContext(client_id=client_id, agent_id=agent_id, session_id=session_id, project_id=project_id, participant_id=participant_id)
    validate_request_context(identity, context, repo_root)
    return MCPService(repo_root).execute_capability("proposal.list", context, {"limit": limit}).model_dump()
