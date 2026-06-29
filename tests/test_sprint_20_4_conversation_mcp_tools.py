from __future__ import annotations

from pathlib import Path

from ageix_mcp.tool_definitions import MCP_TOOL_DEFINITIONS
from models.capability_request import CapabilityRequest
from services.capabilities.conversation_capabilities import register_capabilities
from services.capability_execution_service import CapabilityExecutionService

PARTICIPANTS = [
    {"client_id": "ageix-connector-claude-ai", "agent_role": "claude.ai", "session_id": "sess-architect"},
    {"client_id": "ageix-connector-claude-code", "agent_role": "claude.code", "session_id": "sess-worker"},
    {"client_id": "ageix-connector-chatgpt", "agent_role": "lex", "session_id": "sess-lex"},
]

CONVERSATION_CAPABILITY_IDS = (
    "conversation.open",
    "conversation.transition",
    "conversation.get",
    "conversation.turn.append",
    "conversation.turn.list",
    "conversation.participant.list",
    "conversation.participant.obligations",
    "conversation.handoff.create",
    "conversation.handoff.get",
)


def _tool_by_capability() -> dict[str, object]:
    return {tool.capability_id: tool for tool in MCP_TOOL_DEFINITIONS}


def test_catalog_exposes_conversation_tools() -> None:
    tools = _tool_by_capability()
    for capability_id in CONVERSATION_CAPABILITY_IDS:
        assert capability_id in tools
        assert tools[capability_id].name == f"ageix.{capability_id}"
        assert tools[capability_id].description


def test_conversation_capability_plugin_registers_handlers(tmp_path: Path) -> None:
    registered = {definition.capability_id: handler for definition, handler in register_capabilities(tmp_path)}
    for capability_id in CONVERSATION_CAPABILITY_IDS:
        assert capability_id in registered
        assert callable(registered[capability_id])


def _execute(tmp_path: Path, capability_id: str, arguments: dict) -> dict:
    response = CapabilityExecutionService(tmp_path).execute(CapabilityRequest(
        capability_id=capability_id,
        session_id="sess-lex",
        agent_id="lex",
        arguments=arguments,
    ))
    return {"success": response.success, "result": response.result, "error": response.error}


def test_conversation_lifecycle_through_capability_execution(tmp_path: Path) -> None:
    opened = _execute(tmp_path, "conversation.open", {
        "client_id": "ageix-connector-chatgpt",
        "agent_role": "lex",
        "participants": PARTICIPANTS,
        "project_id": "Ageix",
    })
    assert opened["success"] is True
    conversation_id = opened["result"]["conversation_id"]
    assert opened["result"]["state"] == "OPEN"

    transitioned = _execute(tmp_path, "conversation.transition", {
        "client_id": "ageix-connector-chatgpt",
        "agent_role": "lex",
        "conversation_id": conversation_id,
        "new_state": "ACTIVE",
    })
    assert transitioned["success"] is True
    assert transitioned["result"]["state"] == "ACTIVE"

    appended = _execute(tmp_path, "conversation.turn.append", {
        "client_id": "ageix-connector-chatgpt",
        "agent_role": "lex",
        "session_id": "sess-lex",
        "conversation_id": conversation_id,
        "turn_type": "STATEMENT",
        "content": "Routing the request to the worker.",
        "confidence": 6.0,
    })
    assert appended["success"] is True
    assert appended["result"]["speaker_client_id"] == "ageix-connector-chatgpt"
    assert appended["result"]["speaker_agent_role"] == "lex"

    listed = _execute(tmp_path, "conversation.turn.list", {
        "client_id": "ageix-connector-chatgpt",
        "agent_role": "lex",
        "conversation_id": conversation_id,
    })
    assert listed["success"] is True
    assert len(listed["result"]["turns"]) == 1

    fetched = _execute(tmp_path, "conversation.get", {
        "client_id": "ageix-connector-chatgpt",
        "agent_role": "lex",
        "conversation_id": conversation_id,
    })
    assert fetched["success"] is True
    assert fetched["result"]["state"] == "ACTIVE"
    assert len(fetched["result"]["recent_turns"]) == 1

    participants = _execute(tmp_path, "conversation.participant.list", {
        "client_id": "ageix-connector-chatgpt",
        "agent_role": "lex",
        "conversation_id": conversation_id,
    })
    assert participants["success"] is True
    assert len(participants["result"]["participants"]) == 3

    obligations = _execute(tmp_path, "conversation.participant.obligations", {
        "client_id": "ageix-connector-chatgpt",
        "agent_role": "lex",
        "conversation_id": conversation_id,
    })
    assert obligations["success"] is True
    assert obligations["result"]["obligations"] == {}

    handoff = _execute(tmp_path, "conversation.handoff.create", {
        "client_id": "ageix-connector-chatgpt",
        "agent_role": "lex",
        "conversation_id": conversation_id,
        "requested_action": "Review the worker's diff before merge.",
    })
    assert handoff["success"] is True
    handoff_id = handoff["result"]["handoff_id"]
    assert handoff["result"]["requested_action"] == "Review the worker's diff before merge."

    fetched_handoff = _execute(tmp_path, "conversation.handoff.get", {
        "client_id": "ageix-connector-chatgpt",
        "agent_role": "lex",
        "handoff_id": handoff_id,
    })
    assert fetched_handoff["success"] is True
    assert fetched_handoff["result"]["handoff_id"] == handoff_id


def test_directive_turn_restricted_to_greg(tmp_path: Path) -> None:
    opened = _execute(tmp_path, "conversation.open", {
        "client_id": "ageix-connector-chatgpt",
        "agent_role": "lex",
        "participants": PARTICIPANTS,
        "project_id": "Ageix",
    })
    conversation_id = opened["result"]["conversation_id"]

    denied = _execute(tmp_path, "conversation.turn.append", {
        "client_id": "ageix-connector-chatgpt",
        "agent_role": "lex",
        "session_id": "sess-lex",
        "conversation_id": conversation_id,
        "turn_type": "DIRECTIVE",
        "content": "Do this now.",
        "confidence": 8.0,
    })
    assert denied["success"] is False
    assert denied["error"] == "directive_turns_restricted_to_greg"


def test_conversation_get_unknown_id_returns_error(tmp_path: Path) -> None:
    result = _execute(tmp_path, "conversation.get", {
        "client_id": "ageix-connector-chatgpt",
        "agent_role": "lex",
        "conversation_id": "CONV-DOES-NOT-EXIST",
    })
    assert result["success"] is False
    assert "Unknown conversation_id" in result["error"]
