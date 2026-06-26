from __future__ import annotations

from uuid import uuid4

from models.public_exposure import ForwardedHeaderContext, GovernanceContextSnapshot, RequestCorrelationContext


class RequestCorrelationService:
    """Preserves request identity across proxy, API, governance, and audit layers."""

    def from_forwarded_headers(self, headers: ForwardedHeaderContext) -> RequestCorrelationContext:
        api_request_id = headers.x_request_id or f"ageix-{uuid4().hex}"
        return RequestCorrelationContext(
            proxy_request_id=headers.x_request_id,
            api_request_id=api_request_id,
            governance_request_id=f"gov-{api_request_id}",
            audit_correlation_id=f"audit-{api_request_id}",
        )

    def attach_to_governance(self, *, context: GovernanceContextSnapshot, correlation: RequestCorrelationContext) -> GovernanceContextSnapshot:
        return context.model_copy(update={"correlation_id": correlation.audit_correlation_id})
