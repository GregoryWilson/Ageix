from chair import run_devworker_with_evidence
from chair import build_devworker_packet
from agents.dev_worker_agent import normalize_devworker_result


def test_build_devworker_packet_allows_create_files_when_requested():
    repository_result = {
        "evidence": [],
        "dependency_hints": [],
    }

    packet = build_devworker_packet(
        objective="Create new service",
        target_files=["services/new_service.py"],
        repository_result=repository_result,
        step_constraints={
            "allow_create_files": True,
        },
    )

    constraints = packet["constraints"]

    assert constraints["allow_create_files"] is True
    assert "create_file" in constraints["allowed_operations"]
    assert "replace_file" in constraints["allowed_operations"]


def test_build_devworker_packet_disallows_create_files_by_default():
    repository_result = {
        "evidence": [],
        "dependency_hints": [],
    }

    packet = build_devworker_packet(
        objective="Modify service",
        target_files=["services/example.py"],
        repository_result=repository_result,
    )

    constraints = packet["constraints"]

    assert "replace_file" in constraints["allowed_operations"]
    assert "create_file" not in constraints["allowed_operations"]


def test_run_devworker_with_evidence_allows_create_files_on_retry(monkeypatch):
    captured = {}

    def fake_dispatch_agent(agent_name, payload):
        captured["agent_name"] = agent_name
        captured["payload"] = payload

        return {
            "deliverable": {
                "result_type": "patch_proposal",
                "objective": "Create missing file",
                "summary": "Create file",
                "files_considered": ["services/new_service.py"],
                "evidence_used": [],
                "dependency_hints_used": [],
                "assumptions": [],
                "dependency_risks": [],
                "changes": [
                    {
                        "operation": "create_file",
                        "path": "services/new_service.py",
                        "content": "def hello():\n    return 'world'\n",
                    }
                ],
                "test_plan": ["pytest"],
                "notes": [],
                "no_write_confirmation": True,
            }
        }

    monkeypatch.setattr("chair.dispatch_agent", fake_dispatch_agent)

    result = run_devworker_with_evidence(
        evidence_packet={
            "objective": "Create missing file",
            "target_files": ["services/new_service.py"],
            "evidence": [],
            "dependency_hints": [],
        }
    )

    payload = captured["payload"]
    constraints = payload["constraints"]

    assert captured["agent_name"] == "dev_worker"
    assert constraints["allow_create_files"] is True
    assert "create_file" in constraints["allowed_operations"]
    assert "replace_file" in constraints["allowed_operations"]
    assert result["deliverable"]["result_type"] == "patch_proposal"


def test_normalize_devworker_result_populates_summary():
    packet = {
        "objective": "Create test file"
    }

    data = {
        "result_type": "patch_proposal",
        "changes": []
    }

    result = normalize_devworker_result(data, packet)

    assert "summary" in result
    assert result["summary"]

def test_build_devworker_packet_includes_success_criteria():
    packet = build_devworker_packet(
        objective='smoke_message returns "create_file smoke passed"',
        target_files=["services/smoke_service.py"],
        repository_result={"evidence": [], "dependency_hints": []},
        success_criteria=['smoke_message returns "create_file smoke passed"'],
    )

    assert packet["success_criteria"] == [
        'smoke_message returns "create_file smoke passed"'
    ]


def test_run_devworker_with_evidence_retries_failed_quality_validation(monkeypatch):
    calls = []

    def fake_dispatch_agent(agent_name, payload):
        calls.append(payload)
        literal = (
            "Smoke test successful!"
            if len(calls) == 1
            else "create_file smoke passed"
        )
        return {
            "deliverable": {
                "result_type": "patch_proposal",
                "objective": 'smoke_message returns "create_file smoke passed"',
                "summary": "Create smoke service",
                "files_considered": ["services/smoke_service.py"],
                "evidence_used": [],
                "dependency_hints_used": [],
                "assumptions": [],
                "dependency_risks": [],
                "changes": [
                    {
                        "operation": "create_file",
                        "path": "services/smoke_service.py",
                        "content": f"def smoke_message():\n    return \"{literal}\"\n",
                    },
                    *([] if len(calls) == 1 else [
                        {
                            "operation": "create_file",
                            "path": "tests/test_smoke_service.py",
                            "content": "from services.smoke_service import smoke_message\n\ndef test_smoke_message():\n    assert smoke_message() == \"create_file smoke passed\"\n",
                        }
                    ]),
                ],
                "test_plan": ["pytest"],
                "notes": [],
                "no_write_confirmation": True,
            }
        }

    monkeypatch.setattr("chair.dispatch_agent", fake_dispatch_agent)

    result = run_devworker_with_evidence(
        evidence_packet={
            "objective": 'smoke_message returns "create_file smoke passed"',
            "target_files": ["services/smoke_service.py", "tests/test_smoke_service.py"],
            "success_criteria": ['smoke_message returns "create_file smoke passed"'],
            "evidence": [],
            "dependency_hints": [],
        }
    )

    assert len(calls) == 2
    assert calls[1]["quality_retry"] is True
    assert "create_file smoke passed" in calls[1]["quality_feedback"]
    assert result["deliverable"]["changes"][0]["content"].count(
        "create_file smoke passed"
    ) == 1
    assert result["patch_id"]


def test_run_devworker_with_evidence_blocks_after_quality_retry_failure(monkeypatch):
    def fake_dispatch_agent(agent_name, payload):
        return {
            "deliverable": {
                "result_type": "patch_proposal",
                "objective": 'smoke_message returns "create_file smoke passed"',
                "summary": "Create smoke service",
                "files_considered": ["services/smoke_service.py"],
                "evidence_used": [],
                "dependency_hints_used": [],
                "assumptions": [],
                "dependency_risks": [],
                "changes": [
                    {
                        "operation": "create_file",
                        "path": "services/smoke_service.py",
                        "content": "def smoke_message():\n    return \"Smoke test successful!\"\n",
                    }
                ],
                "test_plan": ["pytest"],
                "notes": [],
                "no_write_confirmation": True,
            }
        }

    monkeypatch.setattr("chair.dispatch_agent", fake_dispatch_agent)

    result = run_devworker_with_evidence(
        evidence_packet={
            "objective": 'smoke_message returns "create_file smoke passed"',
            "target_files": ["services/smoke_service.py"],
            "success_criteria": ['smoke_message returns "create_file smoke passed"'],
            "evidence": [],
            "dependency_hints": [],
        }
    )

    assert result["chair_action"] == "patch_proposal_quality_rejected"
    assert result["status"] == "rejected"
    assert result["quality_result"]["status"] == "fail"
