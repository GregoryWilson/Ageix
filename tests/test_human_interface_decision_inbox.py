from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from human_interface_adapter import router
from services.human_interface_decision_inbox_service import HumanInterfaceDecisionInboxService


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _snapshot_files(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_decision_inbox_requires_project_id() -> None:
    response = _client().get("/human-interface/decision-inbox", headers={"Authorization": "Bearer test"})

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"] == "project_id_required"
    assert payload["records"] == []
    assert payload["read_only"] is True


def test_decision_inbox_denies_incorrect_project_id() -> None:
    response = _client().get("/human-interface/decision-inbox?project_id=Other", headers={"Authorization": "Bearer test"})

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"] == "project_scope_denied"
    assert payload["required_project_id"] == "Ageix"
    assert payload["records"] == []


def test_decision_inbox_denies_missing_authorization() -> None:
    response = _client().get("/human-interface/decision-inbox?project_id=Ageix")

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"] == "authorization_required"
    assert payload["records"] == []
    assert payload["summary"]["status_label"] == "access_denied"


def test_decision_inbox_returns_summary_first_traceable_shape(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".ageix" / "manifests" / "proposals" / "PROP-123" / "proposal.json",
        {
            "proposal_id": "PROP-123",
            "proposal_version": 1,
            "parent_proposal_id": None,
            "project_id": "Ageix",
            "session_id": "session-1",
            "agent_id": "lex",
            "objective": "Review governed adapter behavior.",
            "proposal_type": "implementation",
            "status": "submitted",
            "created_at": "2026-07-01T10:00:00+00:00",
            "updated_at": "2026-07-01T10:05:00+00:00",
            "linked_evidence": ["EVPKG-TEST"],
            "linked_consultations": [],
            "linked_execution_evidence": [],
            "required_consultations": [],
            "accepted_consultations": [],
            "rejected_consultations": [],
            "satisfied_consultations": [],
            "conditions": [],
            "metadata": {},
        },
    )
    _write_json(
        tmp_path / ".ageix" / "architecture" / "adrs" / "ADR-9999" / "adr.json",
        {
            "adr_id": "ADR-9999",
            "adr_number": "ADR-9999",
            "project_id": "Ageix",
            "title": "Adapter decision pending review",
            "status": "proposed",
            "context": "context",
            "decision": "decision",
            "rationale": "rationale",
            "alternatives_considered": [],
            "consequences": [],
            "tradeoffs": [],
            "future_considerations": [],
            "proposal_id": "PROP-123",
            "evidence_package_ids": ["EVPKG-TEST"],
            "architecture_ids": ["ARCH-AGEIX-HUMANINTERFACE"],
            "revision_ids": [],
            "supersedes_adr_id": None,
            "related_adr_ids": [],
            "created_by": "lex",
            "created_at": "2026-07-01T10:10:00+00:00",
            "approved_by": None,
            "approved_at": None,
            "decision_trace_id": None,
            "metadata": {},
        },
    )
    _write_json(
        tmp_path / ".ageix" / "evidence_packages" / "index.json",
        {
            "schema_version": 1,
            "packages": [
                {
                    "package_id": "EVPKG-TEST",
                    "proposal_id": "PROP-123",
                    "evidence_plan_id": "EVPLAN-TEST",
                    "objective": "Evidence for decision inbox.",
                    "created_at": "2026-07-01T10:15:00+00:00",
                    "freshness_status": "fresh",
                    "project_id": "Ageix",
                }
            ],
        },
    )
    _write_json(
        tmp_path / ".ageix" / "decision_traces" / "index.json",
        {
            "schema_version": 1,
            "traces": [
                {
                    "trace_id": "TRACE-TEST",
                    "decision_id": "DEC-TEST",
                    "decision_type": "governance",
                    "decision_summary": "Recent trace summary.",
                    "outcome": "approved",
                    "proposal_id": "PROP-123",
                    "evidence_package_ids": ["EVPKG-TEST"],
                    "project_id": "Ageix",
                    "created_at": "2026-07-01T10:20:00+00:00",
                }
            ],
        },
    )
    validation = tmp_path / ".ageix" / "architecture" / "validation" / "sprint_26_2_test_validation.md"
    validation.parent.mkdir(parents=True, exist_ok=True)
    validation.write_text("# Validation\n", encoding="utf-8")

    payload = HumanInterfaceDecisionInboxService(tmp_path).get_decision_inbox("Ageix")

    assert list(payload.keys())[:1] == ["summary"]
    assert payload["summary"]["project_id"] == "Ageix"
    assert payload["summary"]["mode"] == "read_only"
    assert payload["summary"]["mutation_controls_exposed"] is False
    assert payload["read_only"] is True
    assert payload["records"]
    assert {record["record_type"] for record in payload["records"]} >= {
        "pending_proposal",
        "pending_architecture_decision",
        "validation_result",
        "recent_decision_trace",
        "evidence_link",
    }
    for record in payload["records"]:
        assert record["record_id"]
        assert record["summary"]
        assert record["status_label"]
        assert record["source"]["system_of_record"] == "Ageix"
        assert "governing_artifact_ids" in record


def test_decision_inbox_does_not_return_executable_mutation_controls(tmp_path: Path) -> None:
    payload = HumanInterfaceDecisionInboxService(tmp_path).get_decision_inbox("Ageix")
    serialized = json.dumps(payload).lower()

    for first, second in [
        ("approve", "url"),
        ("reject", "url"),
        ("defer", "url"),
        ("request_changes", "url"),
        ("mutation", "payload"),
        ("worker", "trigger"),
        ("repository", "write"),
        ("approval", "state"),
    ]:
        assert f"{first}_{second}" not in serialized


def test_decision_inbox_read_only_does_not_mutate_files(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".ageix" / "decision_traces" / "index.json",
        {"schema_version": 1, "traces": []},
    )
    before = _snapshot_files(tmp_path)

    HumanInterfaceDecisionInboxService(tmp_path).get_decision_inbox("Ageix")

    after = _snapshot_files(tmp_path)
    assert after == before
