from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from fastapi import APIRouter, Depends, HTTPException

from models.auth_identity import AuthIdentity
from services.capability_audit_service import CapabilityAuditService
from services.mcp_context import AgeixEnvelope, AgeixExternalRequestContext
from web.auth import get_auth_identity, resolve_request_context
from web.dependencies import get_repo_root

router = APIRouter()


def _external_context(session_id: str, project_id: str) -> AgeixExternalRequestContext:
    try:
        return AgeixExternalRequestContext(session_id=session_id, project_id=project_id)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/audit/recent")
def recent_audit(
    session_id: str,
    project_id: str,
    limit: int = 20,
    identity: AuthIdentity = Depends(get_auth_identity),
    repo_root: Path = Depends(get_repo_root),
) -> dict[str, Any]:
    context = resolve_request_context(identity, _external_context(session_id, project_id), repo_root)
    records = CapabilityAuditService(repo_root).list_records()
    scoped = [
        record for record in records
        if record.get("project_id") == context.project_id
        or record.get("session_id") == context.session_id
        or record.get("agent_id") == context.agent_id
    ]
    return AgeixEnvelope.ok({"records": scoped[-limit:]}, scope={"project_id": context.project_id, "session_id": context.session_id}).model_dump()
