from chair import run_devworker_with_evidence

from chair import build_devworker_packet


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