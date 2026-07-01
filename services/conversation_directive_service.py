from __future__ import annotations

from pathlib import Path
from typing import Any

from models.agent_role import AgentRole
from models.conversation_turn import TurnType
from services.chair_delegation_service import ChairDelegationService
from services.turn_service import TurnService

# The single Chair-only action this temporary bridge authorizes.
DIRECTIVE_ACTION = "conversation.directive.submit"


class ConversationDirectiveService:
    """Submits a single Chair-only DIRECTIVE into a conversation under a Chair
    delegation, per Sprint 25.4.5.

    This is the governed operation that ties a Chair delegation to the existing
    conversation directive restriction. It verifies the delegation, appends the
    DIRECTIVE turn as the delegate (never as the Chair — no impersonation), then
    consumes the single-use delegation, recording the delegation ID in the audit
    trail. It does not weaken the existing rule that DIRECTIVE turns are
    otherwise restricted to Greg.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self._turns = TurnService(self.repo_root)
        self._delegations = ChairDelegationService(self.repo_root)

    def submit_delegated_directive(
        self,
        *,
        conversation_id: str,
        content: str,
        delegate: str,
        delegation_id: str,
        speaker_client_id: str,
        speaker_agent_role: AgentRole | str,
        speaker_session_id: str,
        model_id: str,
        project_id: str = "Ageix",
        confidence: float = 0.0,
        directed_at: str | None = None,
    ) -> dict[str, Any]:
        if not str(conversation_id or "").strip():
            raise ValueError("conversation_id_required")
        if not str(content or "").strip():
            raise ValueError("content_required")
        if not str(delegate or "").strip():
            raise ValueError("delegate_required")
        if not str(delegation_id or "").strip():
            raise ValueError("chair_delegation_id_required")

        role = speaker_agent_role if isinstance(speaker_agent_role, AgentRole) else AgentRole.parse(speaker_agent_role)

        # 1. Governance check: the delegation must authorize this delegate to
        #    perform the directive action (raises with an explicit reason).
        self._delegations.verify(
            delegation_id, delegate=delegate, action=DIRECTIVE_ACTION, project_id=project_id,
        )

        # 2. Append the Chair-only DIRECTIVE as the delegate. TurnService
        #    re-verifies the delegation so the restriction cannot be bypassed.
        turn = self._turns.append_turn(
            conversation_id,
            speaker_client_id=str(speaker_client_id or ""),
            speaker_agent_role=role,
            speaker_session_id=str(speaker_session_id or ""),
            model_id=str(model_id or ""),
            turn_type=TurnType.DIRECTIVE,
            confidence=float(confidence or 0.0),
            content=str(content),
            directed_at=directed_at,
            participant_id=delegate,
            chair_delegation_id=delegation_id,
        )

        # 3. Consume the single-use delegation and record the delegation ID in
        #    the audit trail of the executed operation (the appended turn).
        delegation = self._delegations.consume(
            delegation_id,
            delegate=delegate,
            action=DIRECTIVE_ACTION,
            consumed_for=turn.turn_id,
            project_id=project_id,
            actor_role=role,
        )

        return {
            # JSON-mode so the delegate identity (speaker_agent_role) and turn
            # type serialize to their string values consistently — the directive
            # is unambiguously recorded as authored by the delegate, not Greg.
            "turn": turn.model_dump(mode="json"),
            "delegation": delegation.to_summary(),
            "chair_delegation_id": delegation.delegation_id,
        }
