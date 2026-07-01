from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from models.agent_role import AgentRole
from models.conversation_turn import TurnType
from services.capabilities.chair_delegation_capabilities import register_capabilities
from services.capability_audit_service import CapabilityAuditService
from services.chair_delegation_service import ChairDelegationService
from services.conversation_directive_service import (
    DIRECTIVE_ACTION,
    ConversationDirectiveService,
)
from services.turn_service import TurnService

CHAIR_ACTOR = "greg"
CHAIR_ROLE = AgentRole.AGEIX_CHAIR
DELEGATE = "lex"
DELEGATE_ROLE = AgentRole.LEX
CONV = "CONV-TEST00000001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create(svc: ChairDelegationService, *, actor_id: str = CHAIR_ACTOR, actor_role: AgentRole = CHAIR_ROLE,
            delegate: str = DELEGATE, actions=None, ttl: int = 30, project_id: str = "Ageix"):
    return svc.create_delegation(
        delegate=delegate,
        allowed_actions=actions or [DIRECTIVE_ACTION],
        actor_id=actor_id,
        actor_role=actor_role,
        project_id=project_id,
        reason="Authorize Lex to submit one Chair directive (no Human Interface yet).",
        expires_in_minutes=ttl,
    )


def _expire(svc: ChairDelegationService, delegation_id: str) -> None:
    d = svc.get_delegation(delegation_id)
    d.expires_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    svc._save(d, append_to_index=False)


def _submit(directives: ConversationDirectiveService, delegation_id: str, *, delegate: str = DELEGATE,
            content: str = "Proceed with the approved plan.", conversation_id: str = CONV):
    return directives.submit_delegated_directive(
        conversation_id=conversation_id,
        content=content,
        delegate=delegate,
        delegation_id=delegation_id,
        speaker_client_id="ageix-connector-lex",
        speaker_agent_role=DELEGATE_ROLE,
        speaker_session_id="sess-lex",
        model_id="lex",
    )


# ---------------------------------------------------------------------------
# Creation requires explicit Chair approval
# ---------------------------------------------------------------------------

def test_chair_can_create_delegation(tmp_path: Path) -> None:
    svc = ChairDelegationService(tmp_path)
    delegation = _create(svc)
    assert delegation.delegation_id.startswith("CHAIRDLG-")
    assert delegation.delegator == CHAIR_ACTOR
    assert delegation.delegate == DELEGATE
    assert delegation.status == "active"
    assert delegation.single_use is True
    assert delegation.allowed_actions == [DIRECTIVE_ACTION]
    assert (tmp_path / ".ageix" / "chair_delegations" / f"{delegation.delegation_id}.json").exists()


def test_governance_role_can_create_delegation(tmp_path: Path) -> None:
    svc = ChairDelegationService(tmp_path)
    delegation = svc.create_delegation(
        delegate=DELEGATE, allowed_actions=[DIRECTIVE_ACTION],
        actor_id="chair-agent", actor_role=AgentRole.AGEIX_CHAIR,
    )
    assert delegation.status == "active"


def test_non_chair_cannot_create_delegation(tmp_path: Path) -> None:
    svc = ChairDelegationService(tmp_path)
    with pytest.raises(ValueError, match="chair_delegation_requires_chair"):
        svc.create_delegation(
            delegate=DELEGATE, allowed_actions=[DIRECTIVE_ACTION],
            actor_id="lex", actor_role=AgentRole.LEX,
        )


def test_create_requires_delegate_and_actions(tmp_path: Path) -> None:
    svc = ChairDelegationService(tmp_path)
    with pytest.raises(ValueError, match="chair_delegation_delegate_required"):
        svc.create_delegation(delegate="", allowed_actions=[DIRECTIVE_ACTION], actor_id=CHAIR_ACTOR, actor_role=CHAIR_ROLE)
    with pytest.raises(ValueError, match="chair_delegation_allowed_actions_required"):
        svc.create_delegation(delegate=DELEGATE, allowed_actions=[], actor_id=CHAIR_ACTOR, actor_role=CHAIR_ROLE)


def test_create_rejects_multiple_actions(tmp_path: Path) -> None:
    svc = ChairDelegationService(tmp_path)
    with pytest.raises(ValueError, match="chair_delegation_single_action_only"):
        svc.create_delegation(
            delegate=DELEGATE, allowed_actions=[DIRECTIVE_ACTION, "conversation.transition"],
            actor_id=CHAIR_ACTOR, actor_role=CHAIR_ROLE,
        )


# ---------------------------------------------------------------------------
# Verification gates
# ---------------------------------------------------------------------------

def test_verify_passes_for_valid_delegation(tmp_path: Path) -> None:
    svc = ChairDelegationService(tmp_path)
    d = _create(svc)
    verified = svc.verify(d.delegation_id, delegate=DELEGATE, action=DIRECTIVE_ACTION)
    assert verified.delegation_id == d.delegation_id


def test_verify_rejects_delegate_mismatch(tmp_path: Path) -> None:
    svc = ChairDelegationService(tmp_path)
    d = _create(svc)
    with pytest.raises(ValueError, match="chair_delegation_delegate_mismatch"):
        svc.verify(d.delegation_id, delegate="someone-else", action=DIRECTIVE_ACTION)


def test_verify_rejects_unauthorized_action(tmp_path: Path) -> None:
    svc = ChairDelegationService(tmp_path)
    d = _create(svc)
    with pytest.raises(ValueError, match="chair_delegation_action_not_authorized"):
        svc.verify(d.delegation_id, delegate=DELEGATE, action="conversation.transition")


def test_verify_rejects_expired(tmp_path: Path) -> None:
    svc = ChairDelegationService(tmp_path)
    d = _create(svc)
    _expire(svc, d.delegation_id)
    with pytest.raises(ValueError, match="chair_delegation_expired"):
        svc.verify(d.delegation_id, delegate=DELEGATE, action=DIRECTIVE_ACTION)


def test_verify_rejects_project_mismatch(tmp_path: Path) -> None:
    svc = ChairDelegationService(tmp_path)
    d = _create(svc, project_id="Ageix")
    with pytest.raises(ValueError, match="chair_delegation_project_mismatch"):
        svc.verify(d.delegation_id, delegate=DELEGATE, action=DIRECTIVE_ACTION, project_id="Other")


def test_verify_unknown_delegation(tmp_path: Path) -> None:
    svc = ChairDelegationService(tmp_path)
    with pytest.raises(ValueError, match="chair_delegation_not_found"):
        svc.verify("CHAIRDLG-DOESNOTEXIST", delegate=DELEGATE, action=DIRECTIVE_ACTION)


# ---------------------------------------------------------------------------
# End-to-end: delegated Chair directive workflow
# ---------------------------------------------------------------------------

def test_full_workflow_delegated_directive(tmp_path: Path) -> None:
    delegations = ChairDelegationService(tmp_path)
    directives = ConversationDirectiveService(tmp_path)

    # 1. Chair creates the delegation.
    d = _create(delegations)

    # 2. Lex submits a Chair-only directive using it.
    result = _submit(directives, d.delegation_id)
    turn = result["turn"]

    # 3. Governance validated: the DIRECTIVE turn exists, posted by Lex (not Greg),
    #    and carries the authorizing delegation id.
    assert turn["turn_type"] == TurnType.DIRECTIVE.value
    assert turn["speaker_agent_role"] == AgentRole.LEX.value
    assert turn["chair_delegation_id"] == d.delegation_id
    assert result["chair_delegation_id"] == d.delegation_id

    # 5. The delegation is consumed.
    consumed = delegations.get_delegation(d.delegation_id)
    assert consumed.status == "consumed"
    assert consumed.consumed_by == DELEGATE
    assert consumed.consumed_for == turn["turn_id"]


def test_audit_records_reference_delegation(tmp_path: Path) -> None:
    delegations = ChairDelegationService(tmp_path)
    directives = ConversationDirectiveService(tmp_path)
    d = _create(delegations)
    result = _submit(directives, d.delegation_id)

    records = CapabilityAuditService(tmp_path).list_records()
    # Both the creation and the consumption are audited and reference the id.
    create_records = [r for r in records if r["capability_id"] == "chair.delegation.create"]
    consume_records = [r for r in records if r["capability_id"] == "chair.delegation.consume"]
    assert any(r["metadata"]["delegation_id"] == d.delegation_id for r in create_records)
    assert consume_records
    consume = consume_records[-1]
    assert consume["metadata"]["delegation_id"] == d.delegation_id
    assert consume["metadata"]["consumed_for"] == result["turn"]["turn_id"]
    assert consume["metadata"]["delegate"] == DELEGATE


# ---------------------------------------------------------------------------
# Single-use / reuse prevention
# ---------------------------------------------------------------------------

def test_second_use_is_rejected(tmp_path: Path) -> None:
    delegations = ChairDelegationService(tmp_path)
    directives = ConversationDirectiveService(tmp_path)
    d = _create(delegations)
    _submit(directives, d.delegation_id)
    with pytest.raises(ValueError, match="chair_delegation_already_consumed"):
        _submit(directives, d.delegation_id)


def test_expired_delegation_cannot_submit(tmp_path: Path) -> None:
    delegations = ChairDelegationService(tmp_path)
    directives = ConversationDirectiveService(tmp_path)
    d = _create(delegations)
    _expire(delegations, d.delegation_id)
    with pytest.raises(ValueError, match="chair_delegation_expired"):
        _submit(directives, d.delegation_id)


# ---------------------------------------------------------------------------
# Governance not weakened / no impersonation
# ---------------------------------------------------------------------------

def test_directive_still_restricted_without_delegation(tmp_path: Path) -> None:
    # The existing Chair-only rule is preserved: a non-Greg identity cannot post
    # a DIRECTIVE without a delegation.
    turns = TurnService(tmp_path)
    with pytest.raises(ValueError, match="directive_turns_restricted_to_greg"):
        turns.append_turn(
            CONV,
            speaker_client_id="ageix-connector-lex",
            speaker_agent_role=AgentRole.LEX,
            speaker_session_id="sess-lex",
            model_id="lex",
            turn_type=TurnType.DIRECTIVE,
            confidence=0.0,
            content="Unauthorized directive.",
            participant_id="lex",
        )


def test_append_turn_with_bogus_delegation_is_rejected(tmp_path: Path) -> None:
    # A bare/forged delegation id cannot bypass the restriction: TurnService
    # re-verifies against the governed delegation store.
    turns = TurnService(tmp_path)
    with pytest.raises(ValueError, match="chair_delegation_not_found"):
        turns.append_turn(
            CONV,
            speaker_client_id="ageix-connector-lex",
            speaker_agent_role=AgentRole.LEX,
            speaker_session_id="sess-lex",
            model_id="lex",
            turn_type=TurnType.DIRECTIVE,
            confidence=0.0,
            content="Forged authority.",
            participant_id="lex",
            chair_delegation_id="CHAIRDLG-FORGED0001",
        )


def test_delegation_does_not_impersonate_chair(tmp_path: Path) -> None:
    delegations = ChairDelegationService(tmp_path)
    directives = ConversationDirectiveService(tmp_path)
    d = _create(delegations)
    result = _submit(directives, d.delegation_id)
    # The speaker is Lex — the delegate acts as itself, never as Greg/Chair.
    assert result["turn"]["speaker_agent_role"] == AgentRole.LEX.value
    assert result["turn"]["speaker_agent_role"] != AgentRole.AGEIX_CHAIR.value


def test_greg_direct_directive_still_works(tmp_path: Path) -> None:
    # The bridge does not disturb Greg's own direct Chair directive path.
    turns = TurnService(tmp_path)
    turn = turns.append_turn(
        CONV,
        speaker_client_id="ageix-connector-greg",
        speaker_agent_role=AgentRole.AGEIX_CHAIR,
        speaker_session_id="sess-greg",
        model_id="greg",
        turn_type=TurnType.DIRECTIVE,
        confidence=0.0,
        content="Chair directive.",
        participant_id="greg",
    )
    assert turn.turn_type is TurnType.DIRECTIVE
    assert turn.chair_delegation_id is None


def test_delegation_grant_fields_are_immutable_after_consume(tmp_path: Path) -> None:
    delegations = ChairDelegationService(tmp_path)
    directives = ConversationDirectiveService(tmp_path)
    d = _create(delegations)
    before = d.to_summary()
    _submit(directives, d.delegation_id)
    after = delegations.get_delegation(d.delegation_id)
    # Grant fields unchanged; only consumption status/fields transitioned.
    assert after.delegator == before["delegator"]
    assert after.delegate == before["delegate"]
    assert after.allowed_actions == before["allowed_actions"]
    assert after.expires_at == before["expires_at"]
    assert after.created_at == before["created_at"]
    assert after.status == "consumed"


# ---------------------------------------------------------------------------
# Capability plugin (handlers invoked directly)
# ---------------------------------------------------------------------------

def _handlers(tmp_path: Path) -> dict[str, object]:
    return {definition.capability_id: handler for definition, handler in register_capabilities(tmp_path)}


def test_capability_plugin_registers_bridge_capabilities(tmp_path: Path) -> None:
    handlers = _handlers(tmp_path)
    for capability_id in (
        "chair.delegation.create",
        "chair.delegation.get",
        "chair.delegation.list",
        "conversation.directive.submit",
    ):
        assert capability_id in handlers
        assert callable(handlers[capability_id])


def test_capability_non_chair_create_denied(tmp_path: Path) -> None:
    handlers = _handlers(tmp_path)
    denied = handlers["chair.delegation.create"]({
        "delegate": DELEGATE, "allowed_actions": [DIRECTIVE_ACTION],
        "actor_id": "lex", "agent_role": "lex",
    })
    assert denied["success"] is False
    assert denied["error"] == "chair_delegation_requires_chair"


def test_capability_end_to_end(tmp_path: Path) -> None:
    handlers = _handlers(tmp_path)
    created = handlers["chair.delegation.create"]({
        "delegate": DELEGATE, "allowed_action": DIRECTIVE_ACTION,
        "actor_id": "greg", "agent_role": "ageix.chair",
        "reason": "one directive",
    })
    assert created["success"] is True
    delegation_id = created["result"]["delegation_id"]

    submitted = handlers["conversation.directive.submit"]({
        "conversation_id": CONV,
        "content": "Approve and proceed.",
        "delegation_id": delegation_id,
        "participant_id": DELEGATE,
        "client_id": "ageix-connector-lex",
        "agent_role": "lex",
        "session_id": "sess-lex",
        "model_id": "lex",
    })
    assert submitted["success"] is True
    assert submitted["result"]["chair_delegation_id"] == delegation_id

    # Reuse fails through the capability surface too.
    reused = handlers["conversation.directive.submit"]({
        "conversation_id": CONV,
        "content": "Second attempt.",
        "delegation_id": delegation_id,
        "participant_id": DELEGATE,
        "client_id": "ageix-connector-lex",
        "agent_role": "lex",
        "session_id": "sess-lex",
        "model_id": "lex",
    })
    assert reused["success"] is False
    assert reused["error"] == "chair_delegation_already_consumed"
