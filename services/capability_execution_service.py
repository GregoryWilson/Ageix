from __future__ import annotations

from pathlib import Path

from models.capability_audit_record import CapabilityAuditRecord
from models.capability_request import CapabilityRequest
from models.capability_response import CapabilityResponse
from services.agent_authorization_service import AgentAuthorizationService
from services.capability_audit_service import CapabilityAuditService
from services.capability_registry_service import CapabilityRegistryService


class CapabilityExecutionService:
    """Executes external agent capability requests through authorization and audit."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.registry = CapabilityRegistryService(self.repo_root)
        self.authorization = AgentAuthorizationService(self.repo_root)
        self.audit = CapabilityAuditService(self.repo_root)

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
            result = handler({
                **request.arguments,
                "session_id": request.session_id,
                "agent_id": request.agent_id,
                "capability_id": request.capability_id,
            })
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
        self.audit.record(CapabilityAuditRecord(
            session_id=request.session_id,
            agent_id=request.agent_id,
            capability_id=request.capability_id,
            success=response.success,
            reason=reason,
        ))
