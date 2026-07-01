from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Header, Query, status
from fastapi.responses import JSONResponse

from services.human_interface_decision_inbox_service import HumanInterfaceDecisionInboxService
from services.human_interface_governed_approval_service import HumanInterfaceGovernedApprovalService


router = APIRouter(prefix="/human-interface", tags=["human-interface"])


@router.get("/decision-inbox")
def decision_inbox(
    project_id: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
):
    """Read-only, project-scoped Human Interface Decision Inbox endpoint.

    The adapter requires explicit project context and a caller authorization
    boundary before returning any governed records. It returns labels and
    traceable identifiers only; it does not expose executable decision controls.
    """
    if not authorization:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "summary": {
                    "project_id": project_id,
                    "mode": "read_only",
                    "record_count": 0,
                    "status_label": "access_denied",
                    "mutation_controls_exposed": False,
                },
                "success": False,
                "error": "authorization_required",
                "project_id": project_id,
                "required_project_id": HumanInterfaceDecisionInboxService.REQUIRED_PROJECT_ID,
                "read_only": True,
                "records": [],
            },
        )

    service = HumanInterfaceDecisionInboxService(".")
    result = service.get_decision_inbox(project_id)
    if result.get("error"):
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content=result)
    return result


@router.post("/decision-action")
def decision_action(
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
    x_ageix_session_id: str | None = Header(default=None),
    x_ageix_agent_id: str | None = Header(default=None),
    x_ageix_client_id: str | None = Header(default=None),
    x_ageix_provider: str | None = Header(default=None),
    x_ageix_agent_role: str | None = Header(default=None),
    x_ageix_participant_id: str | None = Header(default=None),
):
    """Execute a governed decision action by translating to Ageix capabilities.

    The adapter validates request completeness and authenticated boundary only.
    It delegates all authorization, governance mutation, trace, audit, and system
    of record updates to the governed capability infrastructure.
    """
    identity = {
        "authenticated": bool(authorization),
        "session_id": x_ageix_session_id or "human-interface",
        "agent_id": x_ageix_agent_id or "chair",
        "client_id": x_ageix_client_id or "human_interface",
        "provider": x_ageix_provider or "human_interface",
        "agent_role": x_ageix_agent_role or "ageix.chair",
        "participant_id": x_ageix_participant_id,
        "project_id": payload.get("project_id"),
        "authority_granted": False,
    }
    service = HumanInterfaceGovernedApprovalService(".")
    result = service.execute(payload, identity)
    if result.get("success"):
        return result

    error = str(result.get("error") or "governance_rejection")
    if error in {"authorization_required", "authorization_failure", "project_scope_denied", "invalid_project"}:
        response_status = status.HTTP_403_FORBIDDEN
    elif error in {"capability_unavailable"}:
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        response_status = status.HTTP_400_BAD_REQUEST
    return JSONResponse(status_code=response_status, content=result)
