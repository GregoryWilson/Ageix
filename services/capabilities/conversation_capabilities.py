from __future__ import annotations

from pathlib import Path
from typing import Any

from models.capability_definition import CapabilityDefinition
from models.conversation import ConversationState
from models.conversation_turn import TurnType
from services.conversation_service import ConversationService
from services.handoff_service import HandoffService
from services.participant_service import ParticipantService
from services.turn_service import TurnService


def register_capabilities(repo_root: Path):
    def conversations() -> ConversationService:
        return ConversationService(repo_root)

    def turns() -> TurnService:
        return TurnService(repo_root)

    def participants() -> ParticipantService:
        return ParticipantService(repo_root)

    def handoffs() -> HandoffService:
        return HandoffService(repo_root)

    def conversation_open(arguments: dict[str, Any]) -> dict[str, Any]:
        invitees = arguments.get("participants") or []
        if not invitees:
            return {"success": False, "result": {}, "error": "participants_required"}
        conversation = conversations().open_conversation(
            invitees,
            project_id=arguments.get("project_id"),
            metadata=dict(arguments.get("metadata") or {}),
        )
        return {"success": True, "result": conversation.model_dump(), "metadata": {"source": "conversation_service"}}

    def conversation_transition(arguments: dict[str, Any]) -> dict[str, Any]:
        conversation_id = str(arguments.get("conversation_id") or "")
        new_state = str(arguments.get("new_state") or "")
        if not conversation_id:
            return {"success": False, "result": {}, "error": "conversation_id_required"}
        if not new_state:
            return {"success": False, "result": {}, "error": "new_state_required"}
        try:
            conversation = conversations().transition_state(conversation_id, ConversationState(new_state))
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": conversation.model_dump(), "metadata": {"source": "conversation_service"}}

    def conversation_get(arguments: dict[str, Any]) -> dict[str, Any]:
        conversation_id = str(arguments.get("conversation_id") or "")
        if not conversation_id:
            return {"success": False, "result": {}, "error": "conversation_id_required"}
        try:
            result = conversations().get_conversation(conversation_id, recent_turn_limit=int(arguments.get("recent_turn_limit") or 10))
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": result, "metadata": {"source": "conversation_service"}}

    def conversation_turn_append(arguments: dict[str, Any]) -> dict[str, Any]:
        conversation_id = str(arguments.get("conversation_id") or "")
        turn_type = str(arguments.get("turn_type") or "")
        content = str(arguments.get("content") or "")
        if not conversation_id:
            return {"success": False, "result": {}, "error": "conversation_id_required"}
        if not turn_type:
            return {"success": False, "result": {}, "error": "turn_type_required"}
        if not content:
            return {"success": False, "result": {}, "error": "content_required"}
        try:
            turn = turns().append_turn(
                conversation_id,
                speaker_client_id=str(arguments.get("client_id") or ""),
                speaker_agent_role=str(arguments.get("agent_role") or ""),
                speaker_session_id=str(arguments.get("session_id") or ""),
                model_id=str(arguments.get("model_id") or arguments.get("agent_id") or ""),
                turn_type=TurnType(turn_type),
                confidence=float(arguments.get("confidence") or 0.0),
                content=content,
                directed_at=arguments.get("directed_at"),
                participant_id=arguments.get("participant_id"),
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": turn.model_dump(), "metadata": {"source": "turn_service"}}

    def conversation_turn_list(arguments: dict[str, Any]) -> dict[str, Any]:
        conversation_id = str(arguments.get("conversation_id") or "")
        if not conversation_id:
            return {"success": False, "result": {}, "error": "conversation_id_required"}
        raw_limit = arguments.get("limit")
        result = turns().list_turns(
            conversation_id,
            limit=int(raw_limit) if raw_limit is not None else None,
            offset=int(arguments.get("offset") or 0),
            most_recent=bool(arguments.get("most_recent") or False),
        )
        return {"success": True, "result": {"turns": result}, "metadata": {"source": "turn_service"}}

    def conversation_participant_list(arguments: dict[str, Any]) -> dict[str, Any]:
        conversation_id = str(arguments.get("conversation_id") or "")
        if not conversation_id:
            return {"success": False, "result": {}, "error": "conversation_id_required"}
        result = [participant.model_dump() for participant in participants().list_participants(conversation_id)]
        return {"success": True, "result": {"participants": result}, "metadata": {"source": "participant_service"}}

    def conversation_participant_obligations(arguments: dict[str, Any]) -> dict[str, Any]:
        conversation_id = str(arguments.get("conversation_id") or "")
        if not conversation_id:
            return {"success": False, "result": {}, "error": "conversation_id_required"}
        result = participants().pending_obligations(conversation_id)
        return {"success": True, "result": {"obligations": result}, "metadata": {"source": "participant_service"}}

    def conversation_handoff_create(arguments: dict[str, Any]) -> dict[str, Any]:
        conversation_id = str(arguments.get("conversation_id") or "")
        requested_action = str(arguments.get("requested_action") or "")
        if not conversation_id:
            return {"success": False, "result": {}, "error": "conversation_id_required"}
        if not requested_action:
            return {"success": False, "result": {}, "error": "requested_action_required"}
        try:
            package = handoffs().create_handoff(
                conversation_id,
                requested_action=requested_action,
                conversation_summary=str(arguments.get("conversation_summary") or ""),
                outstanding_questions=arguments.get("outstanding_questions") or [],
            )
        except ValueError as exc:
            return {"success": False, "result": {}, "error": str(exc)}
        return {"success": True, "result": package.model_dump(), "metadata": {"source": "handoff_service"}}

    def conversation_handoff_get(arguments: dict[str, Any]) -> dict[str, Any]:
        handoff_id = str(arguments.get("handoff_id") or "")
        if not handoff_id:
            return {"success": False, "result": {}, "error": "handoff_id_required"}
        package = handoffs().get_handoff(handoff_id)
        if package is None:
            return {"success": False, "result": {}, "error": "handoff_not_found"}
        return {"success": True, "result": package.model_dump(), "metadata": {"source": "handoff_service"}}

    return [
        (CapabilityDefinition(
            capability_id="conversation.open",
            category="conversation",
            access_level="governed_read",
            handler="conversation.open",
            description="Open a governed shared conversation with a declared set of participants, per ADR-0016.",
        ), conversation_open),
        (CapabilityDefinition(
            capability_id="conversation.transition",
            category="conversation",
            access_level="governed_read",
            handler="conversation.transition",
            description="Transition a shared conversation's lifecycle state (e.g. ACTIVE, CLOSED, ARCHIVED), per ADR-0016's state machine.",
        ), conversation_transition),
        (CapabilityDefinition(
            capability_id="conversation.get",
            category="conversation",
            access_level="governed_read",
            handler="conversation.get",
            description="Retrieve a shared conversation's state, participants, rules of engagement, and recent turns.",
        ), conversation_get),
        (CapabilityDefinition(
            capability_id="conversation.turn.append",
            category="conversation",
            access_level="governed_read",
            handler="conversation.turn.append",
            description="Append an immutable turn to a shared conversation as the authenticated caller, per ADR-0016.",
        ), conversation_turn_append),
        (CapabilityDefinition(
            capability_id="conversation.turn.list",
            category="conversation",
            access_level="governed_read",
            handler="conversation.turn.list",
            description="List the append-only turn history of a shared conversation.",
        ), conversation_turn_list),
        (CapabilityDefinition(
            capability_id="conversation.participant.list",
            category="conversation",
            access_level="governed_read",
            handler="conversation.participant.list",
            description="List registered participants of a shared conversation.",
        ), conversation_participant_list),
        (CapabilityDefinition(
            capability_id="conversation.participant.obligations",
            category="conversation",
            access_level="governed_read",
            handler="conversation.participant.obligations",
            description="List pending directed-question obligations by agent role for a shared conversation.",
        ), conversation_participant_obligations),
        (CapabilityDefinition(
            capability_id="conversation.handoff.create",
            category="conversation",
            access_level="governed_read",
            handler="conversation.handoff.create",
            description="Serialize a governed HANDOFF_PACKAGE artifact summarizing a shared conversation, per ADR-0016.",
        ), conversation_handoff_create),
        (CapabilityDefinition(
            capability_id="conversation.handoff.get",
            category="conversation",
            access_level="governed_read",
            handler="conversation.handoff.get",
            description="Retrieve one governed HANDOFF_PACKAGE artifact by ID.",
        ), conversation_handoff_get),
    ]
