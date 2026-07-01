from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.capability_request import CapabilityRequest
from services.capability_execution_service import CapabilityExecutionService


class HumanInterfaceGovernedApprovalService:
    """Human Interface translation layer for governed approval execution.

    This service does not approve, reject, defer, request changes, store Open WebUI
    approval state, write repository files directly, invoke Git, or execute workers.
    It validates the Human Interface request shape and delegates execution to the
    governed Ageix capability infrastructure.
    """

    REQUIRED_PROJECT_ID = "Ageix"
    CAPABILITY_ID = "human_interface.approval.execute"
    SUPPORTED_ACTIONS = {
        "approve",
        "reject",
        "defer",
        "request_changes",
        "add_comment",
    }
    ACTION_ALIASES = {
        "approved": "approve",
        "deny": "reject",
        "denied": "reject",
        "deferred": "defer",
        "request-change": "request_changes",
        "request changes": "request_changes",
        "changes_requested": "request_changes",
        "comment": "add_comment",
        "add-comment": "add_comment",
        "add comment": "add_comment",
        "rationale": "add_comment",
    }

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.executor = CapabilityExecutionService(self.repo_root)

    def execute(self, payload: dict[str, Any], authenticated_identity: dict[str, Any] | None) -> dict[str, Any]:
        identity = dict(authenticated_identity or {})
        if not identity.get("authenticated"):
            return self._failure("authorization_required", payload, status_label="access_denied")

        validation_error = self._validate(payload)
        if validation_error:
            return validation_error

        action = self._normalize_action(payload.get("action"))
        arguments = {
            "project_id": str(payload.get("project_id")),
            "target_record_id": str(payload.get("target_record_id")),
            "target_record_type": str(payload.get("target_record_type")),
            "action": action,
            "rationale": str(payload.get("rationale") or "").strip(),
            "client_id": str(identity.get("client_id") or "human_interface"),
            "provider": str(identity.get("provider") or "human_interface"),
            "participant_id": identity.get("participant_id"),
            "agent_role": str(identity.get("agent_role") or "ageix_chair"),
            "authenticated_identity": identity,
        }
        request = CapabilityRequest(
            capability_id=self.CAPABILITY_ID,
            session_id=str(identity.get("session_id") or "human-interface"),
            agent_id=str(identity.get("agent_id") or "chair"),
            arguments=arguments,
        )
        response = self.executor.execute(request)
        if not response.success:
            return {
                "success": False,
                "error": self._normalize_failure_reason(response.error),
                "governance_error": response.error,
                "project_id": payload.get("project_id"),
                "target_record_id": payload.get("target_record_id"),
                "target_record_type": payload.get("target_record_type"),
                "action": action,
                "adapter": "human_interface_governed_approval",
                "capability_id": self.CAPABILITY_ID,
                "mutation_performed_by_adapter": False,
                "timestamp": self._now(),
                "metadata": response.metadata,
            }
        result = dict(response.result or {})
        result.setdefault("success", True)
        result.setdefault("project_id", payload.get("project_id"))
        result.setdefault("target_record_id", payload.get("target_record_id"))
        result.setdefault("target_record_type", payload.get("target_record_type"))
        result.setdefault("action", action)
        result.setdefault("adapter", "human_interface_governed_approval")
        result.setdefault("capability_id", self.CAPABILITY_ID)
        result.setdefault("mutation_performed_by_adapter", False)
        result.setdefault("timestamp", self._now())
        return result

    def _validate(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        for field in ["project_id", "target_record_id", "target_record_type", "action", "rationale"]:
            if not str(payload.get(field) or "").strip():
                return self._failure(f"{field}_required", payload)
        if payload.get("project_id") != self.REQUIRED_PROJECT_ID:
            return self._failure("project_scope_denied", payload)
        action = self._normalize_action(payload.get("action"))
        if action not in self.SUPPORTED_ACTIONS:
            return self._failure("unsupported_action", payload)
        return None

    def _normalize_action(self, action: Any) -> str:
        raw = str(action or "").strip().lower()
        return self.ACTION_ALIASES.get(raw, raw.replace("-", "_").replace(" ", "_"))

    def _failure(self, error: str, payload: dict[str, Any], *, status_label: str = "request_rejected") -> dict[str, Any]:
        return {
            "success": False,
            "error": error,
            "project_id": payload.get("project_id"),
            "required_project_id": self.REQUIRED_PROJECT_ID,
            "target_record_id": payload.get("target_record_id"),
            "target_record_type": payload.get("target_record_type"),
            "action": payload.get("action"),
            "status_label": status_label,
            "adapter": "human_interface_governed_approval",
            "capability_id": self.CAPABILITY_ID,
            "mutation_performed_by_adapter": False,
            "timestamp": self._now(),
        }

    def _normalize_failure_reason(self, error: str | None) -> str:
        value = str(error or "governance_rejection")
        if value in {"unknown_capability", "capability_handler_not_registered"}:
            return "capability_unavailable"
        if "authorization" in value or "denied" in value or "restricted" in value:
            return "authorization_failure"
        if "project" in value:
            return "invalid_project"
        if "not_found" in value:
            return "invalid_target"
        return value

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
