from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.architecture_decision_record import ArchitectureDecisionRecord, ArchitectureDecisionRecordStatus
from models.proposal import ProposalStatus
from services.architecture_decision_record_service import ArchitectureDecisionRecordService
from services.proposal_service import ProposalService


class ArchitectureAdrApprovalService:
    """Target-specific governed Architecture ADR approval execution."""

    CAPABILITY_ID = "architecture.adr.approval.execute"
    REQUIRED_PROJECT_ID = "Ageix"
    SUPPORTED_ACTIONS = {"approve", "reject", "defer", "request_changes", "add_comment"}
    SUPPORTED_TARGET_TYPES = {
        "adr",
        "architecture_decision",
        "architecture_decision_record",
        "pending_architecture_decision",
    }
    MUTABLE_STATUSES = {
        ArchitectureDecisionRecordStatus.DRAFT,
        ArchitectureDecisionRecordStatus.PROPOSED,
    }
    TERMINAL_STATUSES = {
        ArchitectureDecisionRecordStatus.ACCEPTED,
        ArchitectureDecisionRecordStatus.REJECTED,
        ArchitectureDecisionRecordStatus.SUPERSEDED,
        ArchitectureDecisionRecordStatus.DEPRECATED,
    }

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.adrs = ArchitectureDecisionRecordService(self.repo_root)
        self.proposals = ProposalService(self.repo_root)

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        clean = self._validate(arguments)
        if clean.get("error"):
            return clean

        try:
            adr = self.adrs._load_adr(clean["target_record_id"])
        except FileNotFoundError:
            return self._failure("target_not_found", clean)

        if adr.project_id != self.REQUIRED_PROJECT_ID:
            return self._failure("project_scope_denied", clean, status_before=adr.status.value)

        status_before = adr.status.value
        action = clean["action"]

        if action == "approve":
            return self._approve(clean, adr, status_before)
        if action == "reject":
            return self._reject(clean, adr, status_before)
        if action == "add_comment":
            return self._add_comment(clean, adr, status_before)
        if action in {"defer", "request_changes"}:
            return self._failure("unsupported_action_for_target", clean, status_before=status_before, status_after=status_before)
        return self._failure("unsupported_action", clean, status_before=status_before, status_after=status_before)

    def _approve(self, clean: dict[str, Any], adr: ArchitectureDecisionRecord, status_before: str) -> dict[str, Any]:
        if adr.status in self.TERMINAL_STATUSES or adr.status not in self.MUTABLE_STATUSES:
            return self._failure("invalid_target_state", clean, status_before=status_before, status_after=status_before)
        try:
            proposal = self.proposals.get_proposal(adr.proposal_id)
        except FileNotFoundError:
            return self._failure("target_not_found", clean, status_before=status_before, status_after=status_before)
        if proposal.status not in {ProposalStatus.APPROVED, ProposalStatus.APPROVED_WITH_CONDITIONS}:
            return self._failure("invalid_target_state", clean, status_before=status_before, status_after=status_before)

        metadata = self._metadata_with_governance_event(adr.metadata, clean, status_before, ArchitectureDecisionRecordStatus.ACCEPTED.value)
        updated = self.adrs.accept_approved_adr(
            adr.adr_id,
            approved_by=str(clean.get("participant_id") or clean.get("client_id") or "human_interface"),
            metadata=metadata,
        )
        return self._success(clean, status_before, updated.status.value)

    def _reject(self, clean: dict[str, Any], adr: ArchitectureDecisionRecord, status_before: str) -> dict[str, Any]:
        if adr.status in self.TERMINAL_STATUSES or adr.status not in self.MUTABLE_STATUSES:
            return self._failure("invalid_target_state", clean, status_before=status_before, status_after=status_before)
        adr.status = ArchitectureDecisionRecordStatus.REJECTED
        adr.metadata = self._metadata_with_governance_event(adr.metadata, clean, status_before, adr.status.value)
        self.adrs._write(adr)
        return self._success(clean, status_before, adr.status.value)

    def _add_comment(self, clean: dict[str, Any], adr: ArchitectureDecisionRecord, status_before: str) -> dict[str, Any]:
        adr.metadata = self._metadata_with_governance_event(adr.metadata, clean, status_before, status_before)
        self.adrs._write(adr)
        return self._success(
            clean,
            status_before,
            adr.status.value,
            mutation_performed_by_target_capability=True,
            comment_recorded=True,
        )

    def _validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        clean = {
            "project_id": str(arguments.get("project_id") or "").strip(),
            "target_record_id": str(arguments.get("target_record_id") or "").strip(),
            "target_record_type": str(arguments.get("target_record_type") or "").strip().lower(),
            "action": str(arguments.get("action") or "").strip().lower().replace("-", "_").replace(" ", "_"),
            "rationale": str(arguments.get("rationale") or "").strip(),
            "client_id": str(arguments.get("client_id") or "unknown").strip(),
            "provider": str(arguments.get("provider") or "unknown").strip(),
            "participant_id": arguments.get("participant_id"),
            "agent_role": str(arguments.get("agent_role") or "").strip(),
            "authenticated_identity": dict(arguments.get("authenticated_identity") or {}),
        }
        if not clean["project_id"]:
            return self._failure("project_id_required", clean)
        if clean["project_id"] != self.REQUIRED_PROJECT_ID:
            return self._failure("project_scope_denied", clean)
        if not clean["target_record_id"]:
            return self._failure("target_record_id_required", clean)
        if not clean["target_record_type"]:
            return self._failure("target_record_type_required", clean)
        if clean["target_record_type"] not in self.SUPPORTED_TARGET_TYPES:
            return self._failure("invalid_target", clean)
        if not clean["action"]:
            return self._failure("action_required", clean)
        if clean["action"] not in self.SUPPORTED_ACTIONS:
            return self._failure("unsupported_action", clean)
        if not clean["rationale"]:
            return self._failure("rationale_required", clean)
        if AgentRole.parse(clean["agent_role"]) is not AgentRole.AGEIX_CHAIR:
            return self._failure("authorization_failure", clean)
        return clean

    def _metadata_with_governance_event(
        self,
        metadata: dict[str, Any],
        clean: dict[str, Any],
        status_before: str,
        status_after: str,
    ) -> dict[str, Any]:
        existing = dict(metadata or {})
        comments = list(existing.get("governance_comments") or [])
        event = {
            "capability_id": self.CAPABILITY_ID,
            "action": clean["action"],
            "rationale": clean["rationale"],
            "status_before": status_before,
            "status_after": status_after,
            "client_id": clean.get("client_id"),
            "provider": clean.get("provider"),
            "participant_id": clean.get("participant_id"),
            "agent_role": clean.get("agent_role"),
            "recorded_at": self._now(),
        }
        comments.append(event)
        existing["governance_comments"] = comments
        existing["last_governance_action"] = event
        return existing

    def _success(
        self,
        clean: dict[str, Any],
        status_before: str,
        status_after: str,
        *,
        mutation_performed_by_target_capability: bool = True,
        comment_recorded: bool = False,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "result": {
                "success": True,
                "project_id": clean["project_id"],
                "target_record_id": clean["target_record_id"],
                "target_record_type": clean["target_record_type"],
                "action": clean["action"],
                "status_before": status_before,
                "status_after": status_after,
                "mutation_performed_by_human_interface": False,
                "mutation_performed_by_target_capability": mutation_performed_by_target_capability,
                "approval_semantics_implemented_by_human_interface": False,
                "capability_id": self.CAPABILITY_ID,
                "rationale": clean["rationale"],
                "comment_recorded": comment_recorded,
            },
            "metadata": {
                "source": "architecture_adr_approval_service",
                "target_domain": "architecture_adr",
            },
        }

    def _failure(
        self,
        error: str,
        clean: dict[str, Any],
        *,
        status_before: str | None = None,
        status_after: str | None = None,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "result": {
                "success": False,
                "project_id": clean.get("project_id"),
                "target_record_id": clean.get("target_record_id"),
                "target_record_type": clean.get("target_record_type"),
                "action": clean.get("action"),
                "status_before": status_before,
                "status_after": status_after,
                "mutation_performed_by_human_interface": False,
                "mutation_performed_by_target_capability": False,
                "approval_semantics_implemented_by_human_interface": False,
                "capability_id": self.CAPABILITY_ID,
                "rationale": clean.get("rationale"),
                "error": error,
            },
            "error": error,
            "metadata": {
                "source": "architecture_adr_approval_service",
                "target_domain": "architecture_adr",
            },
        }

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
