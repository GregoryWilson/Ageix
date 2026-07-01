from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ageix_mcp.tool_definitions import MCP_TOOL_DEFINITIONS
from ageix_mcp.tool_registry import MCPToolRegistry
from models.capability_request import CapabilityRequest
from models.conversation_turn import TurnType
from services.capability_audit_service import CapabilityAuditService
from services.capability_execution_service import CapabilityExecutionService
from services.chair_delegation_service import ChairDelegationService

DIRECTIVE_ACTION = "conversation.directive.submit"
CONV = "CONV-2551000001"


def _tool_by_capability() -> dict[str, object]:
    return {tool.capability_id: tool for tool in MCP_TOOL_DEFINITIONS}


def _execute(repo: Path, capability_id: str, agent_id: str, arguments: dict) -> dict:
    response = CapabilityExecutionService(repo).execute(CapabilityRequest(
        capability_id=capability_id,
        session_id=f"sess-{agent_id}",
        agent_id=agent_id,
        arguments=arguments,
    ))
    return {"success": response.success, "result": response.result, "error": response.error}


def _create_delegation(repo: Path) -> str:
    created = _execute(repo, "chair.delegation.create", "greg", {
        "actor_id": "greg", "agent_role": "ageix.chair",
        "delegate": "lex", "allowed_action": DIRECTIVE_ACTION, "project_id": "Ageix",
        "reason": "Authorize Lex to submit the queued Sprint 25.5 directive.",
    })
    assert created["success"], created["error"]
    return created["result"]["delegation_id"]


def _submit_directive(repo: Path, delegation_id: str, *, content: str = "Proceed with Sprint 25.5.") -> dict:
    return _execute(repo, "conversation.directive.submit", "lex", {
        "client_id": "ageix-connector-lex", "agent_role": "lex", "participant_id": "lex",
        "conversation_id": CONV, "content": content, "delegation_id": delegation_id,
        "model_id": "lex", "project_id": "Ageix",
    })


# ---------------------------------------------------------------------------
# MCP catalog now exposes the delegated path (the integration gap that was fixed)
# ---------------------------------------------------------------------------

def test_catalog_exposes_delegated_directive_and_delegation_tools() -> None:
    tools = _tool_by_capability()
    for capability_id in (
        "conversation.directive.submit",
        "chair.delegation.create",
        "chair.delegation.get",
        "chair.delegation.list",
    ):
        assert capability_id in tools, f"{capability_id} missing from MCP catalog"
        assert tools[capability_id].description


def test_directive_submit_tool_resolves_in_registry() -> None:
    registry = MCPToolRegistry()
    tool = registry.get("ageix.conversation.directive.submit")
    assert tool is not None
    assert tool.capability_id == "conversation.directive.submit"


def test_turn_append_tool_remains_greg_only_no_delegation_params() -> None:
    tools = _tool_by_capability()
    append_props = set(tools["conversation.turn.append"].input_schema.get("properties", {}))
    # The generic append path is not the delegated path: it exposes no
    # delegation input and is unchanged.
    assert "delegation_id" not in append_props
    assert "chair_delegation_id" not in append_props


# ---------------------------------------------------------------------------
# Governed execution path: turn.append stays Greg-only for DIRECTIVE
# ---------------------------------------------------------------------------

def test_lex_cannot_append_directive_via_turn_append(tmp_path: Path) -> None:
    result = _execute(tmp_path, "conversation.turn.append", "lex", {
        "client_id": "ageix-connector-lex", "agent_role": "lex", "participant_id": "lex",
        "conversation_id": CONV, "turn_type": "DIRECTIVE", "content": "Unauthorized.",
        "confidence": 0.0, "model_id": "lex",
    })
    assert result["success"] is False
    assert result["error"] == "directive_turns_restricted_to_greg"


# ---------------------------------------------------------------------------
# Governed execution path: the delegated directive workflow end-to-end
# ---------------------------------------------------------------------------

def test_greg_creates_delegation_and_lex_submits_directive(tmp_path: Path) -> None:
    delegation_id = _create_delegation(tmp_path)

    submitted = _submit_directive(tmp_path, delegation_id)
    assert submitted["success"] is True, submitted["error"]
    turn = submitted["result"]["turn"]

    # Directive recorded as authored by the delegate (Lex), not Greg.
    assert turn["turn_type"] == TurnType.DIRECTIVE.value
    assert str(turn["speaker_agent_role"]).endswith("lex")
    assert turn["speaker_agent_role"] != "ageix.chair"
    assert turn["chair_delegation_id"] == delegation_id
    assert submitted["result"]["chair_delegation_id"] == delegation_id


def test_audit_trail_references_delegation_id(tmp_path: Path) -> None:
    delegation_id = _create_delegation(tmp_path)
    submitted = _submit_directive(tmp_path, delegation_id)
    turn_id = submitted["result"]["turn"]["turn_id"]

    records = CapabilityAuditService(tmp_path).list_records()
    consume = [r for r in records if r["capability_id"] == "chair.delegation.consume"]
    assert consume, "expected a delegation consume audit record"
    assert consume[-1]["metadata"]["delegation_id"] == delegation_id
    assert consume[-1]["metadata"]["consumed_for"] == turn_id


def test_delegation_consumed_after_success(tmp_path: Path) -> None:
    delegation_id = _create_delegation(tmp_path)
    _submit_directive(tmp_path, delegation_id)
    fetched = _execute(tmp_path, "chair.delegation.get", "greg", {
        "actor_id": "greg", "agent_role": "ageix.chair", "delegation_id": delegation_id,
    })
    assert fetched["result"]["status"] == "consumed"
    assert fetched["result"]["consumed_by"] == "lex"


def test_reuse_of_delegation_fails(tmp_path: Path) -> None:
    delegation_id = _create_delegation(tmp_path)
    first = _submit_directive(tmp_path, delegation_id)
    assert first["success"] is True
    second = _submit_directive(tmp_path, delegation_id, content="Second attempt.")
    assert second["success"] is False
    assert second["error"] == "chair_delegation_already_consumed"


def test_expired_delegation_fails(tmp_path: Path) -> None:
    delegation_id = _create_delegation(tmp_path)
    svc = ChairDelegationService(tmp_path)
    d = svc.get_delegation(delegation_id)
    d.expires_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    svc._save(d, append_to_index=False)

    result = _submit_directive(tmp_path, delegation_id)
    assert result["success"] is False
    assert result["error"] == "chair_delegation_expired"


def test_mismatched_delegate_fails(tmp_path: Path) -> None:
    delegation_id = _create_delegation(tmp_path)
    # A different identity tries to use Lex's delegation.
    result = _execute(tmp_path, "conversation.directive.submit", "mallory", {
        "client_id": "ageix-connector-mallory", "agent_role": "claude.code", "participant_id": "mallory",
        "conversation_id": CONV, "content": "Not mine.", "delegation_id": delegation_id,
        "model_id": "mallory", "project_id": "Ageix",
    })
    assert result["success"] is False
    assert result["error"] == "chair_delegation_delegate_mismatch"


def test_mismatched_project_fails(tmp_path: Path) -> None:
    delegation_id = _create_delegation(tmp_path)  # project Ageix
    result = _execute(tmp_path, "conversation.directive.submit", "lex", {
        "client_id": "ageix-connector-lex", "agent_role": "lex", "participant_id": "lex",
        "conversation_id": CONV, "content": "Wrong project.", "delegation_id": delegation_id,
        "model_id": "lex", "project_id": "OtherProject",
    })
    assert result["success"] is False
    assert result["error"] == "chair_delegation_project_mismatch"
