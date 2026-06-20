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


class ConsultationSubmitPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context: AgeixExternalRequestContext
    proposal_id: str = Field(min_length=1)
    consultation_type: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.post("/consultations")
def submit_consultation(payload: ConsultationSubmitPayload, identity: AuthIdentity = Depends(get_auth_identity), repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    context = resolve_request_context(identity, payload.context, repo_root)
    args = {**payload.arguments, "proposal_id": payload.proposal_id, "consultation_type": payload.consultation_type}
    return MCPService(repo_root).execute_capability("consultation.submit", context, args).model_dump()


@router.get("/consultations/{consultation_id}")
def get_consultation(
    consultation_id: str,
    session_id: str,
    project_id: str,
    identity: AuthIdentity = Depends(get_auth_identity),
    repo_root: Path = Depends(get_repo_root),
) -> dict[str, Any]:
    context = resolve_request_context(identity, _external_context(session_id, project_id), repo_root)
    return MCPService(repo_root).execute_capability("consultation.details", context, {"consultation_id": consultation_id}).model_dump()
