from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from models.evidence_request import EvidenceRequest
from services.controls_service import ControlsService
from services.consultation_session_service import ConsultationSessionService


class ConsultationEvidenceBrokerService:
    """Governed broker for session-scoped evidence dictionary delivery."""

    def __init__(self, repo_root: str = ".") -> None:
        self.repo_root = repo_root
        self.session_service = ConsultationSessionService(repo_root)
        self.controls = ControlsService(repo_root).get_raw_config().get("consultation", {})

    def serve_evidence(self, consultation_id: str, request: EvidenceRequest) -> dict[str, Any]:
        session = self.session_service.load_session(consultation_id)
        self._validate_session_ready(session)
        item = self._find_evidence_item(session, request.requested_evidence_id)
        self._validate_request(session, request, item)

        response = {
            "request_id": request.request_id,
            "requested_evidence_id": request.requested_evidence_id,
            "status": "served",
            "evidence_id": item["evidence_id"],
            "evidence_type": item.get("evidence_type") or item.get("type"),
            "summary": item.get("summary", ""),
            "estimated_tokens": int(item.get("estimated_tokens", 0)),
            "paths": item.get("paths", []),
            "payload": item.get("payload"),
        }
        self.session_service.record_evidence_request(consultation_id, request)
        self.session_service.record_evidence_response(consultation_id, response)
        return response

    def _validate_session_ready(self, session: dict[str, Any]) -> None:
        ready_statuses = {"approved", "waiting_for_participant", "waiting_for_evidence", "response_recorded"}
        if session.get("status") not in ready_statuses or not session.get("approval"):
            raise PermissionError("Consultation evidence may only be served after approval.")

    def _find_evidence_item(self, session: dict[str, Any], evidence_id: str) -> dict[str, Any]:
        dictionary = session.get("evidence_dictionary") or {}
        for item in dictionary.get("items", []):
            if item.get("evidence_id") == evidence_id:
                return item
        raise ValueError("Requested evidence ID is not present in the session evidence dictionary.")

    def _validate_request(self, session: dict[str, Any], request: EvidenceRequest, item: dict[str, Any]) -> None:
        if not item.get("requestable", True):
            raise PermissionError("Requested evidence item is not requestable.")
        if not self.controls.get("allow_followup_evidence_requests", True) and int(request.round_number) > 1:
            raise PermissionError("Follow-up evidence requests are disabled.")
        if int(request.round_number) > int(self.controls.get("max_followup_rounds", 2)):
            raise PermissionError("Evidence request exceeds allowed follow-up rounds.")

        requests = session.get("evidence_requests", [])
        same_round_count = sum(1 for existing in requests if int(existing.get("round_number", 1)) == int(request.round_number))
        if same_round_count >= int(self.controls.get("max_evidence_requests_per_round", 3)):
            raise PermissionError("Evidence request exceeds per-round request limit.")
        if len(requests) >= int(self.controls.get("max_total_requests", 6)):
            raise PermissionError("Evidence request exceeds total request limit.")

        estimated_tokens = int(item.get("estimated_tokens", 0))
        if estimated_tokens > int(self.controls.get("max_evidence_tokens_per_request", 2000)):
            raise PermissionError("Evidence request exceeds per-request token limit.")

        token_usage = session.get("token_usage", {})
        served_tokens = int(token_usage.get("served_evidence_tokens", 0))
        if served_tokens + estimated_tokens > int(self.controls.get("max_total_evidence_tokens", 8000)):
            raise PermissionError("Evidence request exceeds total evidence token budget.")

        self._validate_scope(session, item)

    def _validate_scope(self, session: dict[str, Any], item: dict[str, Any]) -> None:
        proposal = session.get("proposal") or {}
        governance = proposal.get("governance") or {}
        if governance.get("repository_grounded") is False:
            raise PermissionError("Broker cannot serve evidence for unresolved targets.")
        if governance.get("cloud_may_expand_scope") is True:
            raise PermissionError("Broker cannot serve evidence when scope expansion is permitted.")

        paths = [p for p in item.get("paths", []) if isinstance(p, str) and p]
        if not paths or item.get("reference_only", False):
            return

        approved_scope = set(proposal.get("approved_scope_summary") or [])
        if not approved_scope:
            raise PermissionError("Broker cannot serve path-bound evidence without approved scope.")
        normalized_scope = {self._normalize_path(path) for path in approved_scope}
        for path in paths:
            if self._normalize_path(path) not in normalized_scope:
                raise PermissionError("Broker cannot serve evidence outside approved scope.")

    def _normalize_path(self, path: str) -> str:
        normalized = str(PurePosixPath(path))
        if normalized.startswith("../") or normalized == ".." or normalized.startswith("/"):
            raise PermissionError("Broker cannot serve unresolved or unsafe paths.")
        return normalized
