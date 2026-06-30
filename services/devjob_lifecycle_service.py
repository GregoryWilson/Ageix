from __future__ import annotations

from datetime import datetime, timezone

from models.agent_role import AgentRole
from models.devjob import DevJob, DevJobStatus

GREG_ACTOR_ID = "greg"

GOVERNANCE_ROLES = {AgentRole.AGEIX_CHAIR}
REVIEWER_ROLES = {AgentRole.LEX, AgentRole.AGEIX_CHAIR}
DEVWORKER_ROLES = {AgentRole.CLAUDE_CODE}

ALLOWED_TRANSITIONS: dict[DevJobStatus, set[DevJobStatus]] = {
    "draft": {"assigned", "cancelled"},
    "assigned": {"in_progress", "cancelled"},
    "in_progress": {"submitted", "cancelled"},
    "submitted": {"reviewed", "cancelled"},
    "reviewed": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def is_greg(actor_id: str | None) -> bool:
    return str(actor_id or "") == GREG_ACTOR_ID


def authorize_transition(job: DevJob, target_status: DevJobStatus, *, actor_id: str | None, actor_role: AgentRole) -> None:
    """Raises ValueError if the actor is not authorized to move job to target_status.

    Authority rules, per INTENT-0007:
      - Creator (or Greg/governance) may move draft -> assigned.
      - The assigned DevWorker may move assigned -> in_progress and in_progress -> submitted.
      - A reviewer (Lex) or Greg may move submitted -> reviewed.
      - Only Greg or an authorized governance role may move a job to completed or cancelled.
    """
    if target_status == "assigned":
        if not (is_greg(actor_id) or actor_id == job.created_by or actor_role in GOVERNANCE_ROLES):
            raise ValueError("devjob_transition_requires_creator_or_governance")
        return
    if target_status in ("in_progress", "submitted"):
        if not (actor_role in DEVWORKER_ROLES and actor_id == job.assigned_to):
            raise ValueError("devjob_transition_requires_assigned_devworker")
        return
    if target_status == "reviewed":
        if not (is_greg(actor_id) or actor_role in REVIEWER_ROLES):
            raise ValueError("devjob_transition_requires_reviewer_or_greg")
        return
    if target_status in ("completed", "cancelled"):
        if not (is_greg(actor_id) or actor_role in GOVERNANCE_ROLES):
            raise ValueError("devjob_transition_requires_greg_or_governance")
        return
    raise ValueError(f"devjob_unknown_target_status_{target_status}")


def transition(job: DevJob, target_status: DevJobStatus, *, actor_id: str | None, actor_role: AgentRole, note: str = "") -> DevJob:
    current = job.status
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target_status not in allowed:
        raise ValueError(f"invalid_devjob_state_transition_{current}_to_{target_status}")
    authorize_transition(job, target_status, actor_id=actor_id, actor_role=actor_role)
    job.lifecycle_history.append({
        "from_status": current,
        "to_status": target_status,
        "actor_id": actor_id,
        "actor_role": actor_role.value,
        "note": note,
        "transitioned_at": datetime.now(timezone.utc).isoformat(),
    })
    job.status = target_status
    job.updated_at = datetime.now(timezone.utc).isoformat()
    return job
