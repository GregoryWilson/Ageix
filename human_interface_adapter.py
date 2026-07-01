from __future__ import annotations

from fastapi import APIRouter, Header, Query, status
from fastapi.responses import JSONResponse

from services.human_interface_decision_inbox_service import HumanInterfaceDecisionInboxService


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
