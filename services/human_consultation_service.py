from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.capability_request import CapabilityRequest
from models.human_consultation import (
    HumanConsultationRequest,
    HumanConsultationStatus,
    HumanConsultationTargetRecordType,
    HumanConsultationType,
    approval_choices,
    is_valid_human_consultation_id,
)
from services.capability_execution_service import CapabilityExecutionService


class HumanConsultationService:
    """Ageix-owned human consultation state, validation, routing, and lifecycle mutation.

    Open WebUI and Human Interface surfaces may display and submit selected choices,
    but they do not own consultation state and do not mutate target proposal/ADR
    lifecycles directly.
    """

    CAPABILITY_ID = "human.consultation.respond"
    REQUIRED_PROJECT_ID = "Ageix"
    STORE_ROOT = Path(".ageix") / "human_consultations"
    APPROVAL_ROUTE_BY_TARGET = {
        HumanConsultationTargetRecordType.PROPOSAL.value: "proposal.approval.execute",
        HumanConsultationTargetRecordType.ADR.value: "architecture.adr.approval.execute",
    }
    APPROVAL_EXECUTION_CHOICES = {"approve", "reject", "add_comment"}

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.root = self.repo_root / self.STORE_ROOT

    def create_request(self, request: HumanConsultationRequest) -> HumanConsultationRequest:
        if not self._is_valid_consultation_id(request.consultation_id):
            raise ValueError("invalid_consultation_id")
        now = self._now()
        if not request.created_at:
            request.created_at = now
        request.updated_at = now
        self._write(request)
        return request

    def create_approval_request(
        self,
        *,
        project_id: str,
        target_record_type: str,
        target_record_id: str,
        question: str,
        summary: str,
        evidence_links: list[str] | None = None,
        trace_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> HumanConsultationRequest:
        request = HumanConsultationRequest.approval_request(
            project_id=project_id,
            target_record_type=target_record_type,
            target_record_id=target_record_id,
            question=question,
            summary=summary,
            evidence_links=evidence_links,
            trace_ids=trace_ids,
            metadata=metadata,
        )
        return self.create_request(request)

    def get_request(self, consultation_id: str) -> HumanConsultationRequest:
        clean_consultation_id = str(consultation_id or "").strip()
        if not self._is_valid_consultation_id(clean_consultation_id):
            raise ValueError("invalid_consultation_id")
        path = self._path(clean_consultation_id)
        if not path.exists():
            raise FileNotFoundError(clean_consultation_id)
        return HumanConsultationRequest(**json.loads(path.read_text(encoding="utf-8")))

    def list_requests(self, *, project_id: str | None = None, status: str | None = None) -> list[HumanConsultationRequest]:
        if not self.root.exists():
            return []
        requests: list[HumanConsultationRequest] = []
        for path in sorted(self.root.glob("HCONS-*/consultation.json")):
            try:
                request = HumanConsultationRequest(**json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            if project_id and request.project_id != project_id:
                continue
            if status and request.status.value != status:
                continue
            requests.append(request)
        return sorted(requests, key=lambda item: item.updated_at or item.created_at or "", reverse=True)

    def respond(self, arguments: dict[str, Any]) -> dict[str, Any]:
        clean = self._validate_common(arguments)
        if clean.get("error"):
            return clean

        try:
            request = self.get_request(clean["consultation_id"])
        except FileNotFoundError:
            return self._failure("unknown_consultation", clean)

        if request.project_id != self.REQUIRED_PROJECT_ID:
            return self._failure("project_scope_denied", clean)
        if request.status is not HumanConsultationStatus.PENDING:
            return self._failure("consultation_not_pending", clean)

        choice = request.choice_by_id(clean["selected_choice_id"])
        if choice is None:
            return self._failure("invalid_choice", clean, request=request)
        if choice.requires_rationale and not clean["rationale"]:
            return self._failure("rationale_required", clean, request=request)
        if choice.requires_text and not clean["freeform_text"]:
            return self._failure("freeform_text_required", clean, request=request)
        if AgentRole.parse(clean["agent_role"]) is not AgentRole.AGEIX_CHAIR:
            return self._failure("authorization_failure", clean, request=request)

        routed_result: dict[str, Any] | None = None
        routed_capability_id: str | None = None
        selected_choice_id = choice.id
        if self._should_route_approval(request, selected_choice_id):
            routed_capability_id = self.APPROVAL_ROUTE_BY_TARGET[request.context.target_record_type.value]
            routed_result = self._route_approval(request, clean, routed_capability_id, selected_choice_id)
            if not routed_result.get("success"):
                return self._failure(
                    str(routed_result.get("error") or "approval_route_failed"),
                    clean,
                    request=request,
                    routed_capability_id=routed_capability_id,
                    routed_result=routed_result,
                )

        request.status = HumanConsultationStatus.ANSWERED
        request.selected_choice_id = selected_choice_id
        request.rationale = clean["rationale"]
        request.freeform_text = clean["freeform_text"] or None
        request.answered_at = self._now()
        request.updated_at = request.answered_at
        request.response_result = {
            "selected_choice_id": selected_choice_id,
            "routed_capability_id": routed_capability_id,
            "routed_result": routed_result,
            "execution_logic_available": routed_result is not None,
        }
        self._write(request)

        return {
            "success": True,
            "result": {
                "success": True,
                "project_id": request.project_id,
                "consultation_id": request.consultation_id,
                "consultation_type": request.consultation_type.value,
                "selected_choice_id": selected_choice_id,
                "status": request.status.value,
                "system_of_record": request.system_of_record,
                "target_record_type": request.context.target_record_type.value,
                "target_record_id": request.context.target_record_id,
                "routed_capability_id": routed_capability_id,
                "routed_result": routed_result,
                "mutation_performed_by_human_interface": False,
                "approval_semantics_implemented_by_human_consultation": False,
                "open_webui_state_owner": False,
            },
            "metadata": {"source": "human_consultation_service"},
        }

    def decision_choices_for_record(self, *, target_record_type: str, target_record_id: str) -> dict[str, Any]:
        return {
            "consultation_type": HumanConsultationType.APPROVAL.value,
            "target_record_type": target_record_type,
            "target_record_id": target_record_id,
            "system_of_record": "Ageix",
            "state_owner": "Ageix",
            "choices": [choice.model_dump(mode="json") for choice in approval_choices()],
            "mutation_controls_exposed": False,
        }

    def _validate_common(self, arguments: dict[str, Any]) -> dict[str, Any]:
        clean = {
            "project_id": str(arguments.get("project_id") or "").strip(),
            "consultation_id": str(arguments.get("consultation_id") or "").strip(),
            "selected_choice_id": str(arguments.get("selected_choice_id") or "").strip().lower().replace("-", "_").replace(" ", "_"),
            "rationale": str(arguments.get("rationale") or "").strip(),
            "freeform_text": str(arguments.get("freeform_text") or "").strip(),
            "client_id": str(arguments.get("client_id") or "unknown").strip(),
            "provider": str(arguments.get("provider") or "unknown").strip(),
            "participant_id": arguments.get("participant_id"),
            "agent_role": str(arguments.get("agent_role") or "").strip(),
            "session_id": str(arguments.get("session_id") or "human-consultation").strip(),
            "agent_id": str(arguments.get("agent_id") or "chair").strip(),
        }
        if not clean["project_id"]:
            return self._failure("project_id_required", clean)
        if clean["project_id"] != self.REQUIRED_PROJECT_ID:
            return self._failure("project_scope_denied", clean)
        if not clean["consultation_id"]:
            return self._failure("consultation_id_required", clean)
        if not self._is_valid_consultation_id(clean["consultation_id"]):
            return self._failure("invalid_consultation_id", clean)
        if not clean["selected_choice_id"]:
            return self._failure("selected_choice_id_required", clean)
        return clean

    def _should_route_approval(self, request: HumanConsultationRequest, selected_choice_id: str) -> bool:
        return (
            request.consultation_type is HumanConsultationType.APPROVAL
            and request.context.target_record_type.value in self.APPROVAL_ROUTE_BY_TARGET
            and selected_choice_id in self.APPROVAL_EXECUTION_CHOICES
        )

    def _route_approval(
        self,
        request: HumanConsultationRequest,
        clean: dict[str, Any],
        routed_capability_id: str,
        selected_choice_id: str,
    ) -> dict[str, Any]:
        executor = CapabilityExecutionService(self.repo_root)
        response = executor.execute(CapabilityRequest(
            capability_id=routed_capability_id,
            session_id=clean["session_id"],
            agent_id=clean["agent_id"],
            arguments={
                "project_id": request.project_id,
                "target_record_id": request.context.target_record_id,
                "target_record_type": request.context.target_record_type.value,
                "action": selected_choice_id,
                "rationale": clean["rationale"],
                "client_id": clean["client_id"],
                "provider": clean["provider"],
                "participant_id": clean.get("participant_id"),
                "agent_role": clean["agent_role"],
                "consultation_id": request.consultation_id,
                "freeform_text": clean["freeform_text"],
            },
        ))
        return {
            "success": response.success,
            "result": response.result,
            "metadata": response.metadata,
            "error": response.error,
        }

    def _write(self, request: HumanConsultationRequest) -> None:
        if not self._is_valid_consultation_id(request.consultation_id):
            raise ValueError("invalid_consultation_id")
        path = self._path(request.consultation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(request.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")

    def _path(self, consultation_id: str) -> Path:
        clean_consultation_id = str(consultation_id or "").strip()
        if not self._is_valid_consultation_id(clean_consultation_id):
            raise ValueError("invalid_consultation_id")
        return self.root / clean_consultation_id / "consultation.json"

    def _failure(
        self,
        error: str,
        clean: dict[str, Any],
        *,
        request: HumanConsultationRequest | None = None,
        routed_capability_id: str | None = None,
        routed_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "result": {
                "success": False,
                "project_id": clean.get("project_id"),
                "consultation_id": clean.get("consultation_id"),
                "consultation_type": request.consultation_type.value if request else None,
                "selected_choice_id": clean.get("selected_choice_id"),
                "status": request.status.value if request else None,
                "system_of_record": request.system_of_record if request else "Ageix",
                "target_record_type": request.context.target_record_type.value if request else None,
                "target_record_id": request.context.target_record_id if request else None,
                "routed_capability_id": routed_capability_id,
                "routed_result": routed_result,
                "mutation_performed_by_human_interface": False,
                "approval_semantics_implemented_by_human_consultation": False,
                "open_webui_state_owner": False,
                "error": error,
            },
            "error": error,
            "metadata": {"source": "human_consultation_service"},
        }

    def _is_valid_consultation_id(self, consultation_id: str) -> bool:
        return is_valid_human_consultation_id(consultation_id)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
