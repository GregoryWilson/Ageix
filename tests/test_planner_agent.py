import json

from agents import planner_agent


def fake_llm_response(payload):
    return {
        "response": json.dumps(payload),
        "route": "test",
        "model_key": "test_model",
        "model": "test",
        "reason": "unit test",
        "elapsed_ms": 1,
    }


def test_planner_accepts_steps_object(monkeypatch):
    monkeypatch.setattr(
        planner_agent,
        "invoke_llm",
        lambda purpose, prompt: fake_llm_response(
            {
                "objective": "Build thing",
                "strategy": "Do it safely.",
                "steps": [
                    {
                        "id": "step_1",
                        "agent": "dev_worker",
                        "objective": "Create service",
                        "instructions": "Create the service file.",
                    }
                ],
            }
        ),
    )

    result = planner_agent.execute_planner_agent(
        task={"title": "Build thing", "description": "Test task"}
    )

    content = result["content"]

    assert result["validation_error"] is None
    assert content["objective"] == "Build thing"
    assert len(content["steps"]) == 1
    assert content["steps"][0]["agent"] == "dev_worker"


def test_planner_accepts_work_plan_object(monkeypatch):
    monkeypatch.setattr(
        planner_agent,
        "invoke_llm",
        lambda purpose, prompt: fake_llm_response(
            {
                "work_plan": [
                    {
                        "id": "step_1",
                        "agent": "dev_worker",
                        "objective": "Create service",
                        "instructions": "Create the service file.",
                    }
                ]
            }
        ),
    )

    result = planner_agent.execute_planner_agent(
        task={"title": "Objective From Task", "description": "Test task"}
    )

    content = result["content"]

    assert result["validation_error"] is None
    assert content["objective"] == "Objective From Task"
    assert len(content["steps"]) == 1


def test_planner_accepts_raw_step_list(monkeypatch):
    monkeypatch.setattr(
        planner_agent,
        "invoke_llm",
        lambda purpose, prompt: fake_llm_response(
            [
                {
                    "id": "step_1",
                    "agent": "dev_worker",
                    "objective": "Create service",
                    "instructions": "Create the service file.",
                }
            ]
        ),
    )

    result = planner_agent.execute_planner_agent(
        task={"title": "Raw List Objective", "description": "Test task"}
    )

    content = result["content"]

    assert result["validation_error"] is None
    assert content["objective"] == "Raw List Objective"
    assert len(content["steps"]) == 1


def test_planner_preserves_target_files_constraints_and_expected_output(monkeypatch):
    monkeypatch.setattr(
        planner_agent,
        "invoke_llm",
        lambda purpose, prompt: fake_llm_response(
            {
                "objective": "Patch system",
                "strategy": "Use exact files.",
                "steps": [
                    {
                        "id": "step_1",
                        "agent": "dev_worker",
                        "objective": "Patch service",
                        "instructions": "Modify only listed files.",
                        "inputs": {
                            "target_files": [
                                "chair.py",
                                "services/objective_source_service.py",
                            ]
                        },
                        "constraints": {
                            "allowed_operations": ["create_file", "replace_file"]
                        },
                        "expected_output": {
                            "result_type": "patch_proposal"
                        },
                    }
                ],
            }
        ),
    )

    result = planner_agent.execute_planner_agent(
        task={"title": "Patch system", "description": "Test task"}
    )

    step = result["content"]["steps"][0]

    assert result["validation_error"] is None
    assert step["inputs"]["target_files"] == [
        "chair.py",
        "services/objective_source_service.py",
    ]
    assert step["constraints"]["allowed_operations"] == [
        "create_file",
        "replace_file",
    ]
    assert step["expected_output"]["result_type"] == "patch_proposal"


def test_planner_rejects_malformed_json_cleanly(monkeypatch):
    monkeypatch.setattr(
        planner_agent,
        "invoke_llm",
        lambda purpose, prompt: {
            "response": "{ this is not valid json",
            "route": "test",
            "model_key": "test_model",
            "model": "test",
            "reason": "unit test",
            "elapsed_ms": 1,
        },
    )

    result = planner_agent.execute_planner_agent(
        task={"title": "Bad JSON", "description": "Test task"}
    )

    assert result["validation_error"] is not None
    assert result["content"]["objective"] == "Planner Validation Failure"
    assert result["content"]["steps"] == []