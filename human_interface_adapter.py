from __future__ import annotations

from fastapi import APIRouter, Header, Path, Query, status
from fastapi.responses import JSONResponse

from services.human_interface_decision_inbox_service import HumanInterfaceDecisionInboxService


router = APIRouter(prefix="/human-interface", tags=["human-interface"])


def _authorization_denied(project_id: str | None, *, decision_id: str | None = None) -> JSONResponse:
    content = {
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
    }
    if decision_id is not None:
        content["decision_id"] = decision_id
        content["summary"]["decision_id"] = decision_id
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content=content)


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
        return _authorization_denied(project_id)

    service = HumanInterfaceDecisionInboxService(".")
    result = service.get_decision_inbox(project_id)
    if result.get("error"):
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content=result)
    return result


@router.get("/decision-detail/{decision_id}")
def decision_detail(
    decision_id: str = Path(..., min_length=1),
    project_id: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
):
    """Read-only, project-scoped detail surface for a selected Ageix decision record.

    The detail endpoint enriches an existing inbox record with traceable context
    and disabled governed action contract metadata. It does not execute approval,
    rejection, deferral, request-change, comment, worker, validation, repository,
    or Open WebUI state mutations.
    """
    if not authorization:
        return _authorization_denied(project_id, decision_id=decision_id)

    service = HumanInterfaceDecisionInboxService(".")
    result = service.get_decision_detail(decision_id, project_id)
    if result.get("error") == "decision_detail_not_found":
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=result)
    if result.get("error"):
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content=result)
    return result
