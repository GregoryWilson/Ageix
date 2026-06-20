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


class ConsultationSubmitPayload(BaseModel):
    context: AgeixRequestContext
    proposal_id: str = Field(min_length=1)
    consultation_type: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.post("/consultations")
def submit_consultation(payload: ConsultationSubmitPayload, identity: AuthIdentity = Depends(get_auth_identity), repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    validate_request_context(identity, payload.context, repo_root)
    args = {**payload.arguments, "proposal_id": payload.proposal_id, "consultation_type": payload.consultation_type}
    return MCPService(repo_root).execute_capability("consultation.submit", payload.context, args).model_dump()


@router.get("/consultations/{consultation_id}")
def get_consultation(consultation_id: str, client_id: str, agent_id: str, session_id: str, project_id: str, participant_id: str | None = None, identity: AuthIdentity = Depends(get_auth_identity), repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    context = AgeixRequestContext(client_id=client_id, agent_id=agent_id, session_id=session_id, project_id=project_id, participant_id=participant_id)
    validate_request_context(identity, context, repo_root)
    return MCPService(repo_root).execute_capability("consultation.details", context, {"consultation_id": consultation_id}).model_dump()
