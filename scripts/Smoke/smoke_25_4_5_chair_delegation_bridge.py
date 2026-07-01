"""
Smoke test: Temporary Chair Delegation Bridge (Sprint 25.4.5)

Demonstrates the required workflow:

  1. Greg (Chair) creates a delegation authorizing Lex to submit one directive.
  2. Lex submits a Chair-only DIRECTIVE using that delegation.
  3. Governance validates the delegation before the directive is appended.
  4. Audit records reference the delegation.
  5. The single-use delegation is consumed.
  6. A second attempt to reuse it fails correctly.

The delegation grants authority for ONE named action, never identity: Lex acts
as itself. Ageix remains the authoritative store and existing governance (the
Chair-only DIRECTIVE restriction) is preserved.
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

from models.agent_role import AgentRole
from models.conversation_turn import TurnType
from services.capability_audit_service import CapabilityAuditService
from services.chair_delegation_service import ChairDelegationService
from services.conversation_directive_service import DIRECTIVE_ACTION, ConversationDirectiveService
from services.turn_service import TurnService

CHAIR_ACTOR = "greg"
CHAIR_ROLE = AgentRole.AGEIX_CHAIR
DELEGATE = "lex"
DELEGATE_ROLE = AgentRole.LEX
CONV = "CONV-SMOKE00000001"


def main() -> None:
    print("== Smoke: Temporary Chair Delegation Bridge (Sprint 25.4.5) ==")

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        delegations = ChairDelegationService(repo)
        directives = ConversationDirectiveService(repo)
        turns = TurnService(repo)

        # Baseline governance: Lex cannot post a Chair-only DIRECTIVE unaided.
        try:
            turns.append_turn(
                CONV, speaker_client_id="ageix-connector-lex", speaker_agent_role=DELEGATE_ROLE,
                speaker_session_id="sess-lex", model_id="lex", turn_type=TurnType.DIRECTIVE,
                confidence=0.0, content="Unauthorized.", participant_id="lex",
            )
            raise AssertionError("Lex must not post a directive without delegation")
        except ValueError as exc:
            assert "directive_turns_restricted_to_greg" in str(exc)
        print("Baseline PASS: Chair-only DIRECTIVE is restricted to Greg (governance intact)")

        # 1. Greg (Chair) creates the delegation.
        delegation = delegations.create_delegation(
            delegate=DELEGATE,
            allowed_actions=[DIRECTIVE_ACTION],
            actor_id=CHAIR_ACTOR,
            actor_role=CHAIR_ROLE,
            reason="No Human Interface yet; authorize Lex to submit one Chair directive.",
            expires_in_minutes=30,
        )
        print()
        print(f"1. Created delegation {delegation.delegation_id}")
        print(f"   delegator={delegation.delegator}  delegate={delegation.delegate}  "
              f"actions={delegation.allowed_actions}")
        print(f"   status={delegation.status}  single_use={delegation.single_use}  "
              f"expires_at={delegation.expires_at}")

        # 2. Lex submits a Chair-only directive using that delegation.
        result = directives.submit_delegated_directive(
            conversation_id=CONV,
            content="Approved: proceed with Sprint 25.5 implementation.",
            delegate=DELEGATE,
            delegation_id=delegation.delegation_id,
            speaker_client_id="ageix-connector-lex",
            speaker_agent_role=DELEGATE_ROLE,
            speaker_session_id="sess-lex",
            model_id="lex",
        )
        turn = result["turn"]
        print()
        print(f"2. Lex submitted directive turn {turn['turn_id']}")
        print(f"   speaker_agent_role={turn['speaker_agent_role']}  (acts as itself — no impersonation)")
        print(f"   turn_type={turn['turn_type']}  chair_delegation_id={turn['chair_delegation_id']}")

        # 3. Governance validated the delegation before the directive was appended.
        assert turn["turn_type"] == TurnType.DIRECTIVE.value
        assert turn["speaker_agent_role"] == AgentRole.LEX.value
        assert turn["speaker_agent_role"] != AgentRole.AGEIX_CHAIR.value
        assert turn["chair_delegation_id"] == delegation.delegation_id
        print("3. Governance PASS: delegation verified; directive appended as the delegate")

        # 4. Audit records reference the delegation.
        records = CapabilityAuditService(repo).list_records()
        create_audit = [r for r in records if r["capability_id"] == "chair.delegation.create"]
        consume_audit = [r for r in records if r["capability_id"] == "chair.delegation.consume"]
        assert any(r["metadata"]["delegation_id"] == delegation.delegation_id for r in create_audit)
        assert consume_audit and consume_audit[-1]["metadata"]["delegation_id"] == delegation.delegation_id
        assert consume_audit[-1]["metadata"]["consumed_for"] == turn["turn_id"]
        print(f"4. Audit PASS: {len(create_audit)} create + {len(consume_audit)} consume record(s) "
              f"reference {delegation.delegation_id} (consumed_for={turn['turn_id']})")

        # 5. The single-use delegation is consumed.
        consumed = delegations.get_delegation(delegation.delegation_id)
        assert consumed.status == "consumed"
        assert consumed.consumed_by == DELEGATE
        print(f"5. Consumption PASS: delegation status={consumed.status} consumed_by={consumed.consumed_by}")

        # 6. Attempts to reuse it fail correctly.
        try:
            directives.submit_delegated_directive(
                conversation_id=CONV, content="Second directive attempt.", delegate=DELEGATE,
                delegation_id=delegation.delegation_id, speaker_client_id="ageix-connector-lex",
                speaker_agent_role=DELEGATE_ROLE, speaker_session_id="sess-lex", model_id="lex",
            )
            raise AssertionError("Reuse of a single-use delegation must fail")
        except ValueError as exc:
            assert "chair_delegation_already_consumed" in str(exc)
        print("6. Reuse PASS: second submission rejected (chair_delegation_already_consumed)")

    print()
    print("Smoke PASS: Greg explicitly authorized Lex to submit ONE Chair-only directive;")
    print("the delegation was verified, consumed, audited, and cannot be reused. Existing")
    print("Chair authority and governance are preserved; Ageix remains authoritative.")


if __name__ == "__main__":
    main()
