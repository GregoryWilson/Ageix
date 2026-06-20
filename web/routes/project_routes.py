from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from fastapi import APIRouter, Depends, HTTPException

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


@router.get("/projects/current")
def current_project(
    session_id: str,
    project_id: str,
    identity: AuthIdentity = Depends(get_auth_identity),
    repo_root: Path = Depends(get_repo_root),
) -> dict[str, Any]:
    context = resolve_request_context(identity, _external_context(session_id, project_id), repo_root)
    return MCPService(repo_root).execute_capability("project.profile", context, {}).model_dump()
