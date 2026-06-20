import pytest
from pydantic import ValidationError

from models.evidence_request import EvidenceRequest


def test_create_evidence_request():
    request = EvidenceRequest(
        request_id="REQ-001",
        requested_evidence_id="EV-002",
        reason="Need dependency information to evaluate architecture.",
        priority="high",
    )

    assert request.requested_evidence_id == "EV-002"
    assert request.priority == "high"


def test_evidence_request_requires_reason():
    with pytest.raises(ValidationError):
        EvidenceRequest(request_id="REQ-001", requested_evidence_id="EV-002", reason="")


def test_evidence_request_requires_evidence_id():
    with pytest.raises(ValidationError):
        EvidenceRequest(request_id="REQ-001", requested_evidence_id="", reason="Need context")
