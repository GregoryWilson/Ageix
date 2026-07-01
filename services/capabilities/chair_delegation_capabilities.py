from __future__ import annotations

from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.capability_definition import CapabilityDefinition
from services.chair_delegation_service import ChairDelegationService
from services.conversation_directive_service import ConversationDirectiveService

# Temporary Chair delegation bridge (Sprint 25.4.5). Every capability for this
# bridge lives in this one module so the whole feature can be retired by
# removing this file once the Ageix Human Interface is the authoritative path
# for Chair actions.


def register_capabilities(repo_root: Path):
    def delegations() -> ChairDelegationService:
        return ChairDelegationService(repo_root)

    def directives() -> ConversationDirectiveService:
        return ConversationDirectiveService(repo_root)

    def _actor_id(arguments: dict[str, Any]) -> str:
        return str(arguments.get("actor_id") or arguments.get("client_id") or "")

    def _role(arguments: dict[str, Any]) -> AgentRole:
        return AgentRole.parse(str(arguments.get("agent_role") or ""))

    def delegation_create(arguments: dict[str, Any]) -> dict[str, Any]:
        delegate = str(arguments.get("delegate") or "")
        allowed_actions = arguments.get("allowed_actions")
        if isinstance(allowed_actions, str):
            allowed_actions = [allowed_actions]
        if not delegate:
            return {"success": False, "result": {}, "error": "delegate_required"}
        if not allowed_actions:
            single = arguments.get("allowed_action")
            allowed_actions = [single] if single else []
        if not allowed_actions:
            return {"success": False, "result": {}, "error": "allowed_actions_required"}
        try:
            delegation = delegations().create_delegation(
                delegate=delegate,
                allowed_actions=list(allowed_actions),
                actor_id=_actor_id(arguments),
                actor_role=_role(arguments),
                project_id=str(arguments.get("project_id") or "Ageix"),
                reason=str(arguments.get("reason") or ""),
                expires_in_minutes=int(arguments.get("expires_in_minutes") or 30),
                single_use=bool(arguments.get("single_use", True)),
                session_id=str(arguments.get("session_id") or "chair-delegation"),
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": delegation.to_metadata(), "metadata": {"source": "chair_delegation_service"}}

    def delegation_get(arguments: dict[str, Any]) -> dict[str, Any]:
        delegation_id = str(arguments.get("delegation_id") or "")
        if not delegation_id:
            return {"success": False, "result": {}, "error": "delegation_id_required"}
        try:
            delegation = delegations().get_delegation(delegation_id)
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": delegation.to_metadata(), "metadata": {"source": "chair_delegation_service"}}

    def delegation_list(arguments: dict[str, Any]) -> dict[str, Any]:
        raw_limit = arguments.get("limit")
        result = delegations().list_delegations(
            delegate=arguments.get("delegate"),
            status=arguments.get("status"),
            project_id=arguments.get("project_id"),
            limit=int(raw_limit) if raw_limit is not None else 20,
            offset=int(arguments.get("offset") or 0),
        )
        return {"success": True, "result": result, "metadata": {"source": "chair_delegation_service"}}

    def directive_submit(arguments: dict[str, Any]) -> dict[str, Any]:
        conversation_id = str(arguments.get("conversation_id") or "")
        content = str(arguments.get("content") or "")
        delegation_id = str(arguments.get("delegation_id") or "")
        # The delegate acts as itself; participant_id is the acting identity.
        delegate = str(arguments.get("participant_id") or _actor_id(arguments))
        if not conversation_id:
            return {"success": False, "result": {}, "error": "conversation_id_required"}
        if not content:
            return {"success": False, "result": {}, "error": "content_required"}
        if not delegation_id:
            return {"success": False, "result": {}, "error": "delegation_id_required"}
        try:
            result = directives().submit_delegated_directive(
                conversation_id=conversation_id,
                content=content,
                delegate=delegate,
                delegation_id=delegation_id,
                speaker_client_id=str(arguments.get("client_id") or ""),
                speaker_agent_role=str(arguments.get("agent_role") or ""),
                speaker_session_id=str(arguments.get("session_id") or ""),
                model_id=str(arguments.get("model_id") or arguments.get("agent_id") or ""),
                project_id=str(arguments.get("project_id") or "Ageix"),
                confidence=float(arguments.get("confidence") or 0.0),
                directed_at=arguments.get("directed_at"),
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": result, "metadata": {"source": "conversation_directive_service"}}

    return [
        (CapabilityDefinition(
            capability_id="chair.delegation.create",
            category="chair_delegation",
            access_level="governed_read",
            handler="chair.delegation.create",
            description="Create a temporary, single-use Chair delegation authorizing a delegate to perform one narrowly-scoped Chair-only action. Requires explicit Chair approval (Greg or governance). Temporary bridge, Sprint 25.4.5.",
        ), delegation_create),
        (CapabilityDefinition(
            capability_id="chair.delegation.get",
            category="chair_delegation",
            access_level="governed_read",
            handler="chair.delegation.get",
            description="Retrieve a Chair delegation by ID, including status, expiry, and consumption/audit lineage.",
        ), delegation_get),
        (CapabilityDefinition(
            capability_id="chair.delegation.list",
            category="chair_delegation",
            access_level="governed_read",
            handler="chair.delegation.list",
            description="List Chair delegations with optional delegate, status, and project filters.",
        ), delegation_list),
        (CapabilityDefinition(
            capability_id="conversation.directive.submit",
            category="chair_delegation",
            access_level="governed_read",
            handler="conversation.directive.submit",
            description="Submit a single Chair-only DIRECTIVE into a conversation under a valid Chair delegation. Verifies and consumes the delegation and records it in the audit trail; the delegate acts as itself (no impersonation). Temporary bridge, Sprint 25.4.5.",
        ), directive_submit),
    ]
