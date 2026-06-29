from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ageix_mcp.clients.client_admission_policy import ClientAdmissionDecision, MCPClientAdmissionPolicy
from models.agent_role import AgentRole
from services.agent_session_service import AgentSessionService
from services.mcp_context import AgeixRequestContext


@dataclass(frozen=True)
class ClientTrustValidationResult:
    allowed: bool
    reason: str
    security_violation: bool = False
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_admission(cls, decision: ClientAdmissionDecision) -> "ClientTrustValidationResult":
        return cls(decision.allowed, decision.reason, decision.security_violation, decision.to_dict())


class MCPClientTrustValidator:
    """Validates claimed client identity and persisted session continuity."""

    def __init__(self, repo_root: str = ".", policy: MCPClientAdmissionPolicy | None = None) -> None:
        self.repo_root = repo_root
        self.policy = policy or MCPClientAdmissionPolicy()
        self.sessions = AgentSessionService(repo_root)

    def validate(self, context: AgeixRequestContext) -> ClientTrustValidationResult:
        decision = self.policy.evaluate(
            client_id=context.client_id,
            provider=context.provider,
            display_name=context.display_name,
            agent_id=context.agent_id,
            claimed_primary=context.claimed_primary,
            agent_role=context.agent_role.value if context.agent_role is not AgentRole.UNKNOWN else None,
        )
        if not decision.allowed:
            return ClientTrustValidationResult.from_admission(decision)

        session = self.sessions.get_session(context.session_id)
        if session and session.metadata.get("client_context"):
            existing = session.metadata.get("client_context") or {}
            checks = {
                "client_id": context.client_id,
                "provider": context.provider or existing.get("provider"),
                "agent_id": context.agent_id,
            }
            for key, claimed in checks.items():
                if claimed is not None and existing.get(key) is not None and str(existing.get(key)) != str(claimed):
                    return ClientTrustValidationResult(
                        False,
                        "mcp_session_identity_drift_denied",
                        True,
                        {"field": key, "persisted": existing.get(key), "claimed": claimed},
                    )

        return ClientTrustValidationResult(True, "mcp_client_trusted", False, decision.to_dict())

    def build_client_context(self, context: AgeixRequestContext) -> dict[str, Any]:
        definition = self.policy.registry.get(context.client_id)
        return {
            "client_id": context.client_id,
            "display_name": context.display_name or (definition.display_name if definition else ("Lex" if context.client_id.lower() == "chatgpt" else context.client_id)),
            "provider": context.provider or (definition.provider if definition else ("openai" if context.client_id.lower() == "chatgpt" else context.client_id)),
            "agent_id": context.agent_id,
            "agent_role": context.agent_role.value,
            "session_id": context.session_id,
            "project_id": context.project_id,
            "participant_id": context.participant_id,
            "authority_granted": False,
        }
