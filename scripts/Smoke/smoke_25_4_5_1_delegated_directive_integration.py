"""
Smoke test: Delegated Directive Integration Fix (Sprint 25.4.5.1)

Proves the delegated Chair-directive path works through the GOVERNED CAPABILITY
EXECUTION PATH (the same path the MCP surface uses), which is what Sprint 25.4.5
left unwired — conversation.directive.submit was not on the MCP tool catalog, so
callers fell back to the Greg-only conversation.turn.append and were rejected.

Demonstrates the acceptance workflow:
  1. Greg creates/approves a delegation for Lex.
  2. Lex submits the queued Sprint 25.5 directive using the delegation.
  3. The directive lands in the Ageix conversation, authored by Lex.
  4. The delegation is consumed and cannot be reused.
  5. Governance stays traceable and Chair authority is preserved.
"""
from __future__ import annotations

# Allow running from the repo root without PYTHONPATH=. (mirrors other smokes).
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import tempfile
from pathlib import Path

from ageix_mcp.tool_registry import MCPToolRegistry
from models.capability_request import CapabilityRequest
from services.capability_audit_service import CapabilityAuditService
from services.capability_execution_service import CapabilityExecutionService

CONV = "CONV-2551SMOKE01"
DIRECTIVE_ACTION = "conversation.directive.submit"


def run(repo: Path, capability_id: str, agent_id: str, arguments: dict):
    return CapabilityExecutionService(repo).execute(CapabilityRequest(
        capability_id=capability_id, session_id=f"sess-{agent_id}", agent_id=agent_id, arguments=arguments,
    ))


def main() -> None:
    print("== Smoke: Delegated Directive Integration Fix (Sprint 25.4.5.1) ==")

    # 0. The delegated path is now discoverable on the MCP tool catalog.
    registry = MCPToolRegistry()
    tool = registry.get("ageix.conversation.directive.submit")
    assert tool is not None and tool.capability_id == "conversation.directive.submit"
    print("Catalog PASS: ageix.conversation.directive.submit is on the MCP tool catalog "
          f"(-> {tool.capability_id})")

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)

        # Baseline: Lex cannot post a Chair-only DIRECTIVE via turn.append.
        denied = run(repo, "conversation.turn.append", "lex", {
            "client_id": "ageix-connector-lex", "agent_role": "lex", "participant_id": "lex",
            "conversation_id": CONV, "turn_type": "DIRECTIVE", "content": "Unauthorized.",
            "confidence": 0.0, "model_id": "lex",
        })
        assert denied.success is False and denied.error == "directive_turns_restricted_to_greg"
        print("Baseline PASS: Lex DIRECTIVE via conversation.turn.append is rejected "
              "(Greg-only guard preserved)")

        # 1. Greg (Chair) creates the delegation for Lex.
        created = run(repo, "chair.delegation.create", "greg", {
            "actor_id": "greg", "agent_role": "ageix.chair",
            "delegate": "lex", "allowed_action": DIRECTIVE_ACTION, "project_id": "Ageix",
            "reason": "Authorize Lex to submit the queued Sprint 25.5 directive.",
        })
        assert created.success, created.error
        delegation_id = created.result["delegation_id"]
        print(f"1. Greg created delegation {delegation_id} (delegate=lex, action={DIRECTIVE_ACTION})")

        # 2. Lex submits the directive using the delegation (governed path).
        submitted = run(repo, "conversation.directive.submit", "lex", {
            "client_id": "ageix-connector-lex", "agent_role": "lex", "participant_id": "lex",
            "conversation_id": CONV, "content": "Proceed with Sprint 25.5 implementation.",
            "delegation_id": delegation_id, "model_id": "lex", "project_id": "Ageix",
        })
        assert submitted.success, submitted.error
        turn = submitted.result["turn"]
        print(f"2. Lex submitted directive turn {turn['turn_id']}")

        # 3. Directive authored by Lex (not Greg), referencing the delegation.
        assert turn["speaker_agent_role"] == "lex"
        assert turn["turn_type"] == "DIRECTIVE"
        assert turn["chair_delegation_id"] == delegation_id
        print(f"3. Authored PASS: speaker={turn['speaker_agent_role']} "
              f"(not Greg), chair_delegation_id={turn['chair_delegation_id']}")

        # 4. Consumed + audited; reuse fails.
        fetched = run(repo, "chair.delegation.get", "greg", {
            "actor_id": "greg", "agent_role": "ageix.chair", "delegation_id": delegation_id,
        })
        assert fetched.result["status"] == "consumed"
        consume_audit = [r for r in CapabilityAuditService(repo).list_records()
                         if r["capability_id"] == "chair.delegation.consume"]
        assert consume_audit and consume_audit[-1]["metadata"]["delegation_id"] == delegation_id
        print(f"4. Consumed PASS: status={fetched.result['status']}; audit references {delegation_id}")

        reuse = run(repo, "conversation.directive.submit", "lex", {
            "client_id": "ageix-connector-lex", "agent_role": "lex", "participant_id": "lex",
            "conversation_id": CONV, "content": "Second attempt.",
            "delegation_id": delegation_id, "model_id": "lex", "project_id": "Ageix",
        })
        assert reuse.success is False and reuse.error == "chair_delegation_already_consumed"
        print("   Reuse PASS: second submission rejected (chair_delegation_already_consumed)")

    print()
    print("Smoke PASS: delegated Chair directive works through the governed capability")
    print("path; turn.append stays Greg-only; Chair authority preserved and traceable.")


if __name__ == "__main__":
    main()
