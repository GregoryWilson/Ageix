from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from models.auth_identity import AuthIdentity
from services.capability_audit_service import CapabilityAuditService
from services.mcp_context import AgeixEnvelope, AgeixRequestContext
from web.auth import get_auth_identity, validate_request_context
from web.dependencies import get_repo_root

router = APIRouter()


@router.get("/audit/recent")
def recent_audit(client_id: str, agent_id: str, session_id: str, project_id: str, limit: int = 20, participant_id: str | None = None, identity: AuthIdentity = Depends(get_auth_identity), repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    context = AgeixRequestContext(client_id=client_id, agent_id=agent_id, session_id=session_id, project_id=project_id, participant_id=participant_id)
    validate_request_context(identity, context, repo_root)
    records = CapabilityAuditService(repo_root).list_records()
    scoped = [
        record for record in records
        if record.get("project_id") == project_id
        or record.get("session_id") == session_id
        or record.get("agent_id") == agent_id
    ]
    return AgeixEnvelope.ok({"records": scoped[-limit:]}, scope={"project_id": project_id, "session_id": session_id}).model_dump()
