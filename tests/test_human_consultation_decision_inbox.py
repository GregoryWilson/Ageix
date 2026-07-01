from __future__ import annotations

import json
from pathlib import Path

from models.human_consultation import HumanConsultationRequest, HumanConsultationType, missing_context_choices
from models.proposal import Proposal, ProposalStatus, ProposalType
from services.human_consultation_service import HumanConsultationService
from services.human_interface_decision_inbox_service import HumanInterfaceDecisionInboxService
from services.proposal_service import ProposalService


def _snapshot_files(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_decision_inbox_adds_consultation_choices_to_pending_proposal_items(tmp_path: Path) -> None:
    ProposalService(tmp_path).create_proposal(Proposal(
        proposal_id="PROP-HCONS-INBOX",
        project_id="Ageix",
        session_id="session-1",
        agent_id="lex",
        objective="Review inbox consultation choices.",
        proposal_type=ProposalType.IMPLEMENTATION,
        status=ProposalStatus.SUBMITTED,
        metadata={},
    ))

    payload = HumanInterfaceDecisionInboxService(tmp_path).get_decision_inbox("Ageix")

    proposal_record = next(record for record in payload["records"] if record["record_id"] == "PROP-HCONS-INBOX")
    consultation_metadata = proposal_record["consultation_metadata"]
    assert consultation_metadata["system_of_record"] == "Ageix"
    assert consultation_metadata["state_owner"] == "Ageix"
    assert consultation_metadata["mutation_controls_exposed"] is False
    assert {choice["id"] for choice in consultation_metadata["choices"]} >= {"approve", "reject", "add_comment", "other"}
    other = next(choice for choice in consultation_metadata["choices"] if choice["id"] == "other")
    assert other["requires_text"] is True
    assert other["requires_rationale"] is True


def test_decision_inbox_lists_pending_human_consultation_requests(tmp_path: Path) -> None:
    consultation = HumanConsultationService(tmp_path).create_request(HumanConsultationRequest(
        project_id="Ageix",
        consultation_type=HumanConsultationType.MISSING_CONTEXT,
        question="Which context should Ageix use?",
        summary="Missing context decision needed.",
        choices=missing_context_choices(),
    ))

    payload = HumanInterfaceDecisionInboxService(tmp_path).get_decision_inbox("Ageix")

    record = next(record for record in payload["records"] if record["record_id"] == consultation.consultation_id)
    assert record["record_type"] == "pending_human_consultation"
    assert record["consultation_metadata"]["consultation_type"] == "missing_context"
    assert record["source"]["system_of_record"] == "Ageix"
    assert record["consultation_metadata"]["state_owner"] == "Ageix"


def test_decision_inbox_remains_read_only_with_consultation_metadata(tmp_path: Path) -> None:
    HumanConsultationService(tmp_path).create_request(HumanConsultationRequest(
        project_id="Ageix",
        consultation_type=HumanConsultationType.MISSING_CONTEXT,
        question="Which context should Ageix use?",
        summary="Missing context decision needed.",
        choices=missing_context_choices(),
    ))
    before = _snapshot_files(tmp_path)

    payload = HumanInterfaceDecisionInboxService(tmp_path).get_decision_inbox("Ageix")

    after = _snapshot_files(tmp_path)
    assert after == before
    assert payload["read_only"] is True
    assert payload["summary"]["mutation_controls_exposed"] is False
    serialized = json.dumps(payload).lower()
    assert "worker_trigger" not in serialized
    assert "repository_write" not in serialized
    assert "approval_state" not in serialized
