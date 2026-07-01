from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.proposal import ProposalStatus
from services.proposal_service import ProposalService


class ProposalApprovalService:
    """Target-specific governed approval execution for Proposal records."""

    REQUIRED_PROJECT_ID = "Ageix"
    CAPABILITY_ID = "proposal.approval.execute"
    SUPPORTED_TARGET_TYPES = {"proposal", "pending_proposal"}
    SUPPORTED_ACTIONS = {"approve", "reject", "defer", "request_changes", "add_comment"}
    MUTABLE_STATUSES = {
        ProposalStatus.DRAFT,
        ProposalStatus.SUBMITTED,
        ProposalStatus.AWAITING_EVIDENCE,
        ProposalStatus.AWAITING_CONSULTATION,
        ProposalStatus.CONSULTATION_SUBMITTED,
        ProposalStatus.UNDER_REVIEW,
    }

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.proposals = ProposalService(self.repo_root)

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        validation_error = self._validate(arguments)
        if validation_error:
            return validation_error

        target_record_id = str(arguments.get("target_record_id") or "").strip()
        target_record_type = str(arguments.get("target_record_type") or "").strip().lower()
        action = str(arguments.get("action") or "").strip().lower()
        rationale = str(arguments.get("rationale") or "").strip()

        try:
            proposal = self.proposals.get_proposal(target_record_id)
        except FileNotFoundError:
            return self._failure("target_not_found", arguments)

        if proposal.project_id != self.REQUIRED_PROJECT_ID:
            return self._failure("project_scope_denied", arguments, status_before=proposal.status.value)

        status_before = proposal.status.value
        if action == "approve":
            if proposal.status not in self.MUTABLE_STATUSES:
                return self._failure("invalid_target_state", arguments, status_before=status_before)
            proposal = self.proposals.update_status(
                proposal.proposal_id,
                ProposalStatus.APPROVED,
                metadata=self._metadata_with_event(proposal.metadata, action, rationale, arguments),
            )
        elif action == "reject":
            if proposal.status not in self.MUTABLE_STATUSES:
                return self._failure("invalid_target_state", arguments, status_before=status_before)
            proposal = self.proposals.update_status(
                proposal.proposal_id,
                ProposalStatus.DENIED,
                metadata=self._metadata_with_event(proposal.metadata, action, rationale, arguments),
            )
        elif action == "add_comment":
            proposal = self.proposals.update_status(
                proposal.proposal_id,
                proposal.status,
                metadata=self._metadata_with_event(proposal.metadata, action, rationale, arguments),
            )
        elif action in {"defer", "request_changes"}:
            return self._failure("unsupported_action_for_target", arguments, status_before=status_before)
        else:
            return self._failure("unsupported_action", arguments, status_before=status_before)

        return {
            "success": True,
            "project_id": self.REQUIRED_PROJECT_ID,
            "target_record_id": target_record_id,
            "target_record_type": target_record_type,
            "action": action,
            "status_before": status_before,
            "status_after": proposal.status.value,
            "mutation_performed_by_human_interface": False,
            "mutation_performed_by_target_capability": True,
            "capability_id": self.CAPABILITY_ID,
            "rationale": rationale,
        }

    def _validate(self, arguments: dict[str, Any]) -> dict[str, Any] | None:
        project_id = str(arguments.get("project_id") or "").strip()
        target_record_id = str(arguments.get("target_record_id") or "").strip()
        target_record_type = str(arguments.get("target_record_type") or "").strip().lower()
        action = str(arguments.get("action") or "").strip().lower()
        rationale = str(arguments.get("rationale") or "").strip()
        authenticated_identity = arguments.get("authenticated_identity")
        agent_role = str(arguments.get("agent_role") or "").strip()

        if not isinstance(authenticated_identity, dict) or not authenticated_identity.get("authenticated"):
            return self._failure("authorization_required", arguments)
        if agent_role != "ageix.chair":
            return self._failure("authorization_failure", arguments)
        if not project_id:
            return self._failure("project_id_required", arguments)
        if project_id != self.REQUIRED_PROJECT_ID:
            return self._failure("project_scope_denied", arguments)
        if not target_record_id:
            return self._failure("target_record_id_required", arguments)
        if not target_record_type:
            return self._failure("target_record_type_required", arguments)
        if target_record_type not in self.SUPPORTED_TARGET_TYPES:
            return self._failure("invalid_target", arguments)
        if not action:
            return self._failure("action_required", arguments)
        if action not in self.SUPPORTED_ACTIONS:
            return self._failure("unsupported_action", arguments)
        if not rationale:
            return self._failure("rationale_required", arguments)
        return None

    def _metadata_with_event(self, metadata: dict[str, Any], action: str, rationale: str, arguments: dict[str, Any]) -> dict[str, Any]:
        clean = dict(metadata or {})
        events = list(clean.get("governed_approval_events") or [])
        events.append({
            "action": action,
            "rationale": rationale,
            "capability_id": self.CAPABILITY_ID,
            "client_id": arguments.get("client_id"),
            "provider": arguments.get("provider"),
            "participant_id": arguments.get("participant_id"),
            "agent_role": arguments.get("agent_role"),
            "occurred_at": self._now(),
        })
        clean["governed_approval_events"] = events
        return clean

    def _failure(self, error: str, arguments: dict[str, Any], *, status_before: str | None = None) -> dict[str, Any]:
        return {
            "success": False,
            "error": error,
            "project_id": arguments.get("project_id"),
            "target_record_id": arguments.get("target_record_id"),
            "target_record_type": arguments.get("target_record_type"),
            "action": arguments.get("action"),
            "status_before": status_before,
            "status_after": status_before,
            "mutation_performed_by_human_interface": False,
            "mutation_performed_by_target_capability": False,
            "capability_id": self.CAPABILITY_ID,
            "rationale": arguments.get("rationale"),
        }

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
