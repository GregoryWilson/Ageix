from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from pydantic import ValidationError

from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService
from web.dependencies import get_repo_root

router = APIRouter()


@router.get("/projects/current")
def current_project(client_id: str, agent_id: str, session_id: str, project_id: str, participant_id: str | None = None, repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    try:
        context = AgeixRequestContext(client_id=client_id, agent_id=agent_id, session_id=session_id, project_id=project_id, participant_id=participant_id)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MCPService(repo_root).execute_capability("project.profile", context, {}).model_dump()
