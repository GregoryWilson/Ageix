from __future__ import annotations

from datetime import datetime, timezone

from models.agent_role import AgentRole
from models.devjob import DevJob, DevJobStatus

GREG_ACTOR_ID = "greg"

GOVERNANCE_ROLES = {AgentRole.AGEIX_CHAIR}
REVIEWER_ROLES = {AgentRole.LEX, AgentRole.AGEIX_CHAIR}
DEVWORKER_ROLES = {AgentRole.CLAUDE_CODE}

# Lifecycle transitions whose target status must carry a non-empty reason (note).
REASON_REQUIRED_TARGET_STATUSES: set[DevJobStatus] = {"blocked", "declined"}

ALLOWED_TRANSITIONS: dict[DevJobStatus, set[DevJobStatus]] = {
    "draft": {"assigned", "cancelled"},
    "assigned": {"in_progress", "declined", "cancelled"},
    "in_progress": {"submitted", "blocked", "cancelled"},
    "blocked": {"in_progress", "cancelled"},
    "submitted": {"reviewed", "declined", "cancelled"},
    "reviewed": {"completed", "cancelled"},
    "completed": set(),
    "declined": set(),
    "cancelled": set(),
}


def is_greg(actor_id: str | None) -> bool:
    return str(actor_id or "") == GREG_ACTOR_ID


def validate_assignment_fields(job: DevJob) -> None:
    """Raises ValueError if job lacks the fields INTENT-0007 Phase 2 requires for assignment.

    Pure/no I/O: WORKCTX-* existence is validated separately by the registry,
    which is the only layer with access to the work-context store.
    """
    if not str(job.work_context_id or "").strip():
        raise ValueError("devjob_assignment_requires_work_context")
    if not job.acceptance_criteria:
        raise ValueError("devjob_assignment_requires_acceptance_criteria")
    if not job.allowed_paths:
        raise ValueError("devjob_assignment_requires_allowed_paths")
    if not job.prohibited_paths:
        raise ValueError("devjob_assignment_requires_prohibited_paths")
    if not str(job.assigned_to or "").strip():
        raise ValueError("devjob_assignment_requires_assigned_to")


def authorize_transition(job: DevJob, target_status: DevJobStatus, *, actor_id: str | None, actor_role: AgentRole) -> None:
    """Raises ValueError if the actor is not authorized to move job to target_status.

    Authority rules, per INTENT-0007:
      - Creator (or Greg/governance) may move draft -> assigned.
      - The assigned DevWorker may move assigned -> in_progress and in_progress -> submitted.
      - The assigned DevWorker or governance may move in_progress -> blocked and blocked -> in_progress.
      - The assigned DevWorker or governance may decline an assignment (assigned -> declined).
      - A reviewer (Lex) or Greg may move submitted -> reviewed, or decline a submission
        (submitted -> declined).
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
    if target_status == "blocked":
        is_assigned_devworker = actor_role in DEVWORKER_ROLES and actor_id == job.assigned_to
        if not (is_assigned_devworker or is_greg(actor_id) or actor_role in GOVERNANCE_ROLES):
            raise ValueError("devjob_blocked_requires_assigned_devworker_or_governance")
        return
    if target_status == "declined":
        if job.status == "assigned":
            is_assigned_devworker = actor_role in DEVWORKER_ROLES and actor_id == job.assigned_to
            if not (is_assigned_devworker or is_greg(actor_id) or actor_role in GOVERNANCE_ROLES):
                raise ValueError("devjob_declined_requires_assigned_devworker_or_governance")
            return
        if job.status == "submitted":
            if not (is_greg(actor_id) or actor_role in REVIEWER_ROLES):
                raise ValueError("devjob_declined_requires_reviewer_or_greg")
            return
        raise ValueError("devjob_declined_not_applicable_from_status")
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
    if target_status in REASON_REQUIRED_TARGET_STATUSES and not str(note or "").strip():
        raise ValueError(f"devjob_{target_status}_requires_reason")
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
