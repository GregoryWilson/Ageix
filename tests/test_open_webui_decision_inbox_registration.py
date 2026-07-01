from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from human_interface_gateway import app


REGISTRATION_ARTIFACT = Path("open_webui/decision_inbox_openapi.json")
DECISION_INBOX_PATH = "/human-interface/decision-inbox"
MUTATING_METHODS = {"post", "put", "patch", "delete"}
PROHIBITED_OPERATION_FRAGMENTS = {
    "approve",
    "reject",
    "defer",
    "request_changes",
    "worker_trigger",
    "repository_write",
    "approval_state",
}


def _registration_artifact() -> dict:
    return json.loads(REGISTRATION_ARTIFACT.read_text(encoding="utf-8"))


def test_fastapi_openapi_exposes_decision_inbox_as_get_only() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()
    path_item = openapi["paths"][DECISION_INBOX_PATH]
    assert "get" in path_item
    assert MUTATING_METHODS.isdisjoint(path_item)


def test_registration_artifact_is_open_webui_compatible_and_read_only() -> None:
    artifact = _registration_artifact()

    assert artifact["openapi"].startswith("3.")
    assert artifact["paths"][DECISION_INBOX_PATH]
    path_item = artifact["paths"][DECISION_INBOX_PATH]
    assert set(path_item) == {"get"}

    operation = path_item["get"]
    assert operation["operationId"] == "get_ageix_decision_inbox"
    serialized_operation = json.dumps(operation).lower()
    for fragment in PROHIBITED_OPERATION_FRAGMENTS:
        assert fragment not in serialized_operation

    assert artifact["components"]["securitySchemes"]["BearerAuth"]["type"] == "http"
    assert artifact["components"]["securitySchemes"]["BearerAuth"]["scheme"] == "bearer"


def test_registration_artifact_requires_explicit_ageix_project_context() -> None:
    operation = _registration_artifact()["paths"][DECISION_INBOX_PATH]["get"]

    project_parameters = [
        parameter
        for parameter in operation["parameters"]
        if parameter["name"] == "project_id" and parameter["in"] == "query"
    ]

    assert len(project_parameters) == 1
    project_parameter = project_parameters[0]
    assert project_parameter["required"] is True
    assert project_parameter["schema"]["enum"] == ["Ageix"]


def test_open_webui_compatible_request_path_preserves_ageix_denials() -> None:
    client = TestClient(app)

    missing_auth = client.get(f"{DECISION_INBOX_PATH}?project_id=Ageix")
    missing_project = client.get(DECISION_INBOX_PATH, headers={"Authorization": "Bearer test"})
    wrong_project = client.get(f"{DECISION_INBOX_PATH}?project_id=Other", headers={"Authorization": "Bearer test"})

    assert missing_auth.status_code == 403
    assert missing_auth.json()["error"] == "authorization_required"
    assert missing_project.status_code == 403
    assert missing_project.json()["error"] == "project_id_required"
    assert wrong_project.status_code == 403
    assert wrong_project.json()["error"] == "project_scope_denied"


def test_open_webui_compatible_authorized_read_remains_read_only() -> None:
    client = TestClient(app)

    response = client.get(f"{DECISION_INBOX_PATH}?project_id=Ageix", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "Ageix"
    assert payload["read_only"] is True
    assert payload["summary"]["mode"] == "read_only"
    assert payload["summary"]["mutation_controls_exposed"] is False
    serialized_payload = json.dumps(payload).lower()
    for fragment in PROHIBITED_OPERATION_FRAGMENTS:
        assert fragment not in serialized_payload
