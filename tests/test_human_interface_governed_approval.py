from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from human_interface_adapter import router
from models.proposal import Proposal, ProposalStatus, ProposalType
from services.human_interface_decision_inbox_service import HumanInterfaceDecisionInboxService
from services.human_interface_governed_approval_service import HumanInterfaceGovernedApprovalService
from services.proposal_service import ProposalService


def _identity(agent_role: str = "ageix.chair") -> dict:
    return {
        "authenticated": True,
        "session_id": "human-interface-test",
        "agent_id": "chair",
        "client_id": "human_interface",
        "provider": "human_interface",
        "agent_role": agent_role,
        "project_id": "Ageix",
    }


def _proposal(tmp_path: Path, proposal_id: str = "PROP-HI-TEST") -> Proposal:
    proposal = Proposal(
        proposal_id=proposal_id,
        project_id="Ageix",
        session_id="session-1",
        agent_id="lex",
        objective="Review governed approval execution.",
        proposal_type=ProposalType.IMPLEMENTATION,
        status=ProposalStatus.SUBMITTED,
        linked_evidence=[],
        metadata={},
    )
    return ProposalService(tmp_path).create_proposal(proposal)


def _payload(action: str, proposal_id: str = "PROP-HI-TEST") -> dict:
    return {
        "project_id": "Ageix",
        "target_record_id": proposal_id,
        "target_record_type": "proposal",
        "action": action,
        "rationale": f"Governed rationale for {action}.",
    }


def _execute(tmp_path: Path, action: str, proposal_id: str = "PROP-HI-TEST") -> dict:
    _proposal(tmp_path, proposal_id)
    return HumanInterfaceGovernedApprovalService(tmp_path).execute(_payload(action, proposal_id), _identity())


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_governed_approval_approves_proposal_and_records_trace_and_audit(tmp_path: Path) -> None:
    result = _execute(tmp_path, "approve")

    assert result["success"] is True
    assert result["updated_status"] == "approved"
    assert result["decision_trace_identifier"].startswith("TRACE-")
    assert result["audit_reference"].startswith("capability_audit:human_interface.approval.execute:")
    assert result["acting_identity"]["agent_role"] == "ageix.chair"
    assert result["mutation_performed_by_adapter"] is False

    proposal = ProposalService(tmp_path).get_proposal("PROP-HI-TEST")
    assert proposal.status == ProposalStatus.APPROVED
    assert proposal.metadata["last_human_interface_action"] == "approve"

    trace_index = json.loads((tmp_path / ".ageix" / "decision_traces" / "index.json").read_text(encoding="utf-8"))
    assert trace_index["traces"][0]["outcome"] == "approved"
    audit = json.loads((tmp_path / ".ageix" / "instance" / "capability_audit.json").read_text(encoding="utf-8"))
    assert any(record["capability_id"] == "human_interface.approval.execute" and record["success"] for record in audit["records"])


def test_governed_approval_rejects_proposal(tmp_path: Path) -> None:
    result = _execute(tmp_path, "reject")

    assert result["success"] is True
    assert result["updated_status"] == "denied"
    assert ProposalService(tmp_path).get_proposal("PROP-HI-TEST").status == ProposalStatus.DENIED


def test_governed_approval_defers_proposal(tmp_path: Path) -> None:
    result = _execute(tmp_path, "defer")

    assert result["success"] is True
    assert result["updated_status"] == "under_review"
    assert ProposalService(tmp_path).get_proposal("PROP-HI-TEST").status == ProposalStatus.UNDER_REVIEW


def test_governed_approval_requests_changes_and_records_condition(tmp_path: Path) -> None:
    result = _execute(tmp_path, "request_changes")

    assert result["success"] is True
    assert result["updated_status"] == "under_review"
    proposal = ProposalService(tmp_path).get_proposal("PROP-HI-TEST")
    assert proposal.status == ProposalStatus.UNDER_REVIEW
    assert proposal.conditions == ["Governed rationale for request_changes."]


def test_governed_approval_adds_comment_without_status_change(tmp_path: Path) -> None:
    result = _execute(tmp_path, "add_comment")

    assert result["success"] is True
    assert result["updated_status"] == "submitted"
    proposal = ProposalService(tmp_path).get_proposal("PROP-HI-TEST")
    assert proposal.status == ProposalStatus.SUBMITTED
    assert proposal.metadata["human_interface_comments"][0]["action"] == "add_comment"


def test_governed_approval_rejects_missing_rationale_without_mutation(tmp_path: Path) -> None:
    _proposal(tmp_path)
    before = ProposalService(tmp_path).get_proposal("PROP-HI-TEST").model_dump()
    payload = _payload("approve")
    payload["rationale"] = ""

    result = HumanInterfaceGovernedApprovalService(tmp_path).execute(payload, _identity())

    assert result["success"] is False
    assert result["error"] == "rationale_required"
    after = ProposalService(tmp_path).get_proposal("PROP-HI-TEST").model_dump()
    assert after == before
    assert not (tmp_path / ".ageix" / "decision_traces").exists()


def test_governed_approval_rejects_missing_authorization(tmp_path: Path) -> None:
    _proposal(tmp_path)

    result = HumanInterfaceGovernedApprovalService(tmp_path).execute(_payload("approve"), None)

    assert result["success"] is False
    assert result["error"] == "authorization_required"
    assert ProposalService(tmp_path).get_proposal("PROP-HI-TEST").status == ProposalStatus.SUBMITTED


def test_governed_approval_rejects_invalid_project(tmp_path: Path) -> None:
    _proposal(tmp_path)
    payload = _payload("approve")
    payload["project_id"] = "Other"

    result = HumanInterfaceGovernedApprovalService(tmp_path).execute(payload, _identity())

    assert result["success"] is False
    assert result["error"] == "project_scope_denied"
    assert ProposalService(tmp_path).get_proposal("PROP-HI-TEST").status == ProposalStatus.SUBMITTED


def test_governed_approval_rejects_unsupported_action(tmp_path: Path) -> None:
    _proposal(tmp_path)

    result = HumanInterfaceGovernedApprovalService(tmp_path).execute(_payload("escalate"), _identity())

    assert result["success"] is False
    assert result["error"] == "unsupported_action"
    assert ProposalService(tmp_path).get_proposal("PROP-HI-TEST").status == ProposalStatus.SUBMITTED


def test_governed_approval_rejects_invalid_record(tmp_path: Path) -> None:
    result = HumanInterfaceGovernedApprovalService(tmp_path).execute(_payload("approve", "PROP-MISSING"), _identity())

    assert result["success"] is False
    assert result["error"] == "invalid_target"


def test_governed_approval_surfaces_capability_denial(tmp_path: Path) -> None:
    _proposal(tmp_path)

    result = HumanInterfaceGovernedApprovalService(tmp_path).execute(_payload("approve"), _identity(agent_role="lex"))

    assert result["success"] is False
    assert result["error"] == "authorization_failure"
    assert result["governance_error"] == "governed_write_requires_proposal_for_role_lex"
    assert ProposalService(tmp_path).get_proposal("PROP-HI-TEST").status == ProposalStatus.SUBMITTED


def test_decision_action_endpoint_rejects_missing_authorization() -> None:
    response = _client().post("/human-interface/decision-action", json=_payload("approve"))

    assert response.status_code == 403
    assert response.json()["error"] == "authorization_required"


def test_decision_inbox_regression_remains_read_only(tmp_path: Path) -> None:
    _proposal(tmp_path)

    payload = HumanInterfaceDecisionInboxService(tmp_path).get_decision_inbox("Ageix")

    assert payload["read_only"] is True
    assert payload["summary"]["mutation_controls_exposed"] is False
    assert payload["records"][0]["next_governed_action_label"] == "review_through_existing_governance_path"
