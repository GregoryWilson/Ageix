from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.agent_session import AgentSession
from services.agent_session_service import AgentSessionService


class WorkflowStateService:
    """Derives and persists session-scoped workflow state for governed MCP clients.

    Workflow state is advisory context. It never authorizes capability execution.
    """

    STAGE_RECOMMENDATIONS: dict[str, list[str]] = {
        "session_initialized": ["ageix.projects.current", "ageix.proposals.submit"],
        "proposal_submitted": ["ageix.consultations.submit", "ageix.proposals.status"],
        "consultation_submitted": ["ageix.proposals.status", "ageix.consultations.get"],
        "proposal_status_checked": ["ageix.consultations.submit", "ageix.audit.recent"],
        "audit_reviewed": ["ageix.proposals.status"],
    }

    CAPABILITY_STAGE: dict[str, str] = {
        "proposal.submit": "proposal_submitted",
        "proposal.status": "proposal_status_checked",
        "proposal.details": "proposal_reviewed",
        "proposal.list": "proposal_listed",
        "consultation.submit": "consultation_submitted",
        "consultation.details": "consultation_reviewed",
        "consultation.list": "consultation_listed",
        "audit.recent": "audit_reviewed",
        "ageix.health": "health_checked",
    }

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.sessions = AgentSessionService(repo_root)

    def current(
        self,
        session_id: str,
        agent_id: str,
        project_id: str | None = None,
        client_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = {"client_context": client_context} if client_context else None
        session = self.sessions.get_session(session_id) or self.sessions.create_session(session_id, agent_id, project_id=project_id, metadata=metadata)
        if client_context:
            session.metadata["client_context"] = client_context
            self.sessions.save_session(session)
        return self._project(session)

    def record_event(
        self,
        *,
        session_id: str,
        agent_id: str,
        capability_id: str,
        project_id: str | None = None,
        result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        client_context: dict[str, Any] | None = None,
    ) -> AgentSession:
        initial_metadata = {"client_context": client_context} if client_context else None
        session = self.sessions.get_session(session_id) or self.sessions.create_session(session_id, agent_id, project_id=project_id, metadata=initial_metadata)
        now = datetime.now(timezone.utc).isoformat()
        if project_id and not session.project_id:
            session.project_id = project_id
        if client_context:
            session.metadata["client_context"] = client_context
        session.last_activity = now
        session.updated_at = now
        session.last_tool = capability_id
        if capability_id not in session.capabilities_used:
            session.capabilities_used.append(capability_id)

        proposal_id = self._extract_value("proposal_id", result, metadata)
        if proposal_id:
            session.active_proposal_id = str(proposal_id)
        consultation_id = self._extract_value("consultation_id", result, metadata)
        if consultation_id and str(consultation_id) not in session.active_consultation_ids:
            session.active_consultation_ids.append(str(consultation_id))
        session.workflow_stage = self.CAPABILITY_STAGE.get(capability_id, session.workflow_stage)
        self.sessions.save_session(session)
        return session

    def validate_transition(self, capability_id: str, arguments: dict[str, Any], session_id: str) -> tuple[bool, str | None]:
        if capability_id != "consultation.submit":
            return True, None
        if arguments.get("proposal_id"):
            return True, None
        session = self.sessions.get_session(session_id)
        if session and session.active_proposal_id:
            return True, None
        return False, "proposal_id_or_active_proposal_required"

    def fill_context_arguments(self, capability_id: str, arguments: dict[str, Any], session_id: str) -> dict[str, Any]:
        if capability_id != "consultation.submit" or arguments.get("proposal_id"):
            return arguments
        session = self.sessions.get_session(session_id)
        if session and session.active_proposal_id:
            return {**arguments, "proposal_id": session.active_proposal_id}
        return arguments

    def _project(self, session: AgentSession) -> dict[str, Any]:
        recommended = self.STAGE_RECOMMENDATIONS.get(session.workflow_stage, [])
        return {
            "session_id": session.session_id,
            "agent_id": session.agent_id,
            "project_id": session.project_id,
            "workflow_stage": session.workflow_stage,
            "active_proposal_id": session.active_proposal_id,
            "active_consultation_ids": list(session.active_consultation_ids),
            "last_tool": session.last_tool,
            "last_activity": session.last_activity,
            "capabilities_used": list(session.capabilities_used),
            "client_context": session.metadata.get("client_context", {}),
            "recommended_next_tools": recommended,
            "blocked_tools": [
                {
                    "tool": "ageix.validation.scenario.request",
                    "reason": "validation sandbox execution is reserved for Sprint 17",
                }
            ],
            "governance_boundary": {
                "session_context_grants_authority": False,
                "authorization_required_for_execution": True,
                "chair_authority_preserved": True,
            },
        }

    @staticmethod
    def _extract_value(key: str, *containers: dict[str, Any] | None) -> Any:
        for container in containers:
            if not isinstance(container, dict):
                continue
            if key in container:
                return container[key]
            for value in container.values():
                if isinstance(value, dict) and key in value:
                    return value[key]
        return None
