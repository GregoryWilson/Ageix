from __future__ import annotations

from pathlib import Path

from models.capability_audit_record import CapabilityAuditRecord
from models.capability_request import CapabilityRequest
from models.capability_response import CapabilityResponse
from services.agent_authorization_service import AgentAuthorizationService
from services.capability_audit_service import CapabilityAuditService
from services.capability_registry_service import CapabilityRegistryService
from services.agent_session_service import AgentSessionService
from services.workflow_state_service import WorkflowStateService


class CapabilityExecutionService:
    """Executes external agent capability requests through authorization and audit."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.registry = CapabilityRegistryService(self.repo_root)
        self.authorization = AgentAuthorizationService(self.repo_root)
        self.audit = CapabilityAuditService(self.repo_root)
        self.sessions = AgentSessionService(self.repo_root)
        self.workflow = WorkflowStateService(self.repo_root)

    def execute(self, request: CapabilityRequest) -> CapabilityResponse:
        definition = self.registry.lookup(request.capability_id)
        auth = self.authorization.authorize(request.agent_id, definition, request.capability_id)
        if not auth.allowed:
            response = CapabilityResponse(
                success=False,
                result={},
                metadata={
                    "capability_id": request.capability_id,
                    "agent_id": request.agent_id,
                    "session_id": request.session_id,
                    "authorization_reason": auth.reason,
                },
                error=auth.reason,
            )
            self._audit(request, response, auth.reason)
            return response

        handler = self.registry.handler_for(request.capability_id)
        if not handler:
            response = CapabilityResponse(
                success=False,
                result={},
                metadata={"capability_id": request.capability_id},
                error="capability_handler_not_registered",
            )
            self._audit(request, response, "capability_handler_not_registered")
            return response

        try:
            prepared_arguments = dict(request.arguments or {})
            transition_allowed, transition_error = self.workflow.validate_transition(request.capability_id, prepared_arguments, request.session_id)
            if not transition_allowed:
                response = CapabilityResponse(
                    success=False,
                    result={},
                    metadata={"capability_id": request.capability_id, "workflow_transition_denied": True},
                    error=transition_error,
                )
                self._audit(request, response, transition_error or "workflow_transition_denied")
                return response
            prepared_arguments = self.workflow.fill_context_arguments(request.capability_id, prepared_arguments, request.session_id)
            result = handler({
                **prepared_arguments,
                "session_id": request.session_id,
                "agent_id": request.agent_id,
                "capability_id": request.capability_id,
            })
            project_id = prepared_arguments.get("project_id") if isinstance(prepared_arguments, dict) else None
            client_context = dict(prepared_arguments.get("client_context") or {}) or {
                "client_id": str(prepared_arguments.get("client_id") or "unknown"),
                "agent_id": request.agent_id,
                "provider": str(prepared_arguments.get("provider") or ("openai" if str(prepared_arguments.get("client_id") or "").lower() == "chatgpt" else str(prepared_arguments.get("client_id") or "unknown"))),
                "session_id": request.session_id,
                "project_id": str(project_id) if project_id else None,
                "participant_id": prepared_arguments.get("participant_id"),
                "authority_granted": False,
            }
            self.sessions.record_capability_use(
                request.session_id,
                request.agent_id,
                request.capability_id,
                project_id=str(project_id) if project_id and project_id != "current" else None,
                client_context=client_context,
            )
            if bool(result.get("success", True)):
                self.workflow.record_event(
                    session_id=request.session_id,
                    agent_id=request.agent_id,
                    capability_id=request.capability_id,
                    project_id=str(project_id) if project_id and project_id != "current" else None,
                    result=result.get("result", result),
                    metadata=result.get("metadata", {}),
                    client_context=client_context,
                )
            response = CapabilityResponse(
                success=bool(result.get("success", True)),
                result=result.get("result", result),
                metadata={
                    "capability_id": request.capability_id,
                    "access_level": definition.access_level,
                    "category": definition.category,
                    "agent_id": request.agent_id,
                    "session_id": request.session_id,
                    **result.get("metadata", {}),
                },
                error=result.get("error"),
            )
        except Exception as exc:
            response = CapabilityResponse(
                success=False,
                result={},
                metadata={"capability_id": request.capability_id},
                error=str(exc),
            )
        self._audit(request, response, response.error or "executed")
        return response

    def _audit(self, request: CapabilityRequest, response: CapabilityResponse, reason: str) -> None:
        arguments = request.arguments if isinstance(request.arguments, dict) else {}
        self.audit.record(CapabilityAuditRecord(
            session_id=request.session_id,
            agent_id=request.agent_id,
            capability_id=request.capability_id,
            success=response.success,
            reason=reason,
            client_id=str(arguments.get("client_id")) if arguments.get("client_id") else None,
            project_id=str(arguments.get("project_id")) if arguments.get("project_id") else None,
            participant_id=str(arguments.get("participant_id")) if arguments.get("participant_id") else None,
            metadata={"client_user_agent": str(arguments.get("client_user_agent"))} if arguments.get("client_user_agent") else {},
        ))
