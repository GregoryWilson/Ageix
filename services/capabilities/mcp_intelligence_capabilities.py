from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from services.identity_resolution_service import IdentityResolutionService
from services.mcp_context import AgeixRequestContext
from services.workflow_state_service import WorkflowStateService


def register_capabilities(repo_root: Path):
    def workflow_current(arguments: dict[str, Any]) -> dict[str, Any]:
        session_id = str(arguments.get("session_id") or "")
        agent_id = str(arguments.get("agent_id") or "")
        project_id = str(arguments.get("project_id") or "") or None
        if not session_id:
            return {"success": False, "result": {}, "error": "session_id_required"}
        if not agent_id:
            return {"success": False, "result": {}, "error": "agent_id_required"}
        client_context = {
            "client_id": str(arguments.get("client_id") or "unknown"),
            "agent_id": agent_id,
            "provider": str(arguments.get("provider") or "openai" if str(arguments.get("client_id") or "").lower() == "chatgpt" else arguments.get("client_id") or "unknown"),
            "session_id": session_id,
            "project_id": project_id,
            "participant_id": arguments.get("participant_id"),
            "authority_granted": False,
        }
        state = WorkflowStateService(repo_root).current(session_id, agent_id, project_id, client_context=client_context)
        return {"success": True, "result": state, "metadata": {"source": "workflow_state", "workflow_stage": state["workflow_stage"]}}

    def identity_current(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            context = AgeixRequestContext(
                client_id=str(arguments.get("client_id") or "unknown"),
                agent_id=str(arguments.get("agent_id") or "unknown"),
                session_id=str(arguments.get("session_id") or "unknown"),
                project_id=str(arguments.get("project_id") or "unknown"),
                participant_id=arguments.get("participant_id"),
                provider=str(arguments.get("provider")) if arguments.get("provider") else None,
                display_name=str(arguments.get("display_name")) if arguments.get("display_name") else None,
                client_user_agent=str(arguments.get("client_user_agent")) if arguments.get("client_user_agent") else None,
                client_headers=arguments.get("client_headers") if isinstance(arguments.get("client_headers"), dict) else None,
            )
        except Exception as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        auth_method = arguments.get("authentication_method")
        fake_identity = None
        if auth_method:
            from models.auth_identity import AuthIdentity
            fake_identity = AuthIdentity(
                authenticated=True,
                auth_enabled=True,
                authentication_method=str(auth_method),
                client_id=context.client_id,
                agent_id=context.agent_id,
                participant_id=context.participant_id,
                allowed_projects=[context.project_id],
            )
        resolved = IdentityResolutionService(repo_root).resolve(context, fake_identity)
        return {"success": True, "result": resolved, "metadata": {"source": "identity_resolution", "governance_profile": resolved["governance_profile"]}}

    return [
        (CapabilityDefinition(
            capability_id="workflow.current",
            category="workflow",
            access_level="read",
            handler="mcp.workflow_current",
            description="Return advisory MCP workflow state for the current session without granting authority.",
        ), workflow_current),
        (CapabilityDefinition(
            capability_id="identity.current",
            category="identity",
            access_level="read",
            handler="mcp.identity_current",
            description="Return resolved MCP caller identity and governance profile without granting authority.",
        ), identity_current),
    ]
