import json
from pathlib import Path

from agents import planner_agent
from chair import build_devworker_packet, expand_devworker_packet_for_companion_tests, validate_patch_proof_of_delivery
from models.proposal_quality_models import ProposalQualityFailureCode, ProposalQualityResult, ProposalQualityViolation
from services.planner_work_packet_service import PlannerWorkPacketService
from services.worker_profile_service import WorkerProfileService


def fake_llm_response(payload):
    return {
        "response": json.dumps(payload),
        "route": "test",
        "model_key": "test_model",
        "model": "test",
        "reason": "unit test",
        "elapsed_ms": 1,
    }


def discovery_payload():
    return {
        "status": "ready_for_planning",
        "research_results": [
            {
                "confidence": 0.9,
                "claims": [
                    {
                        "claim_id": "R-001",
                        "claim": "Jira Cloud supports API token authentication.",
                        "confidence": 0.9,
                        "source": "research_worker",
                        "implementation_implications": ["Use Jira Cloud API token authentication"],
                    },
                    {
                        "claim_id": "R-002",
                        "claim": "Jira issues can be created through the REST API.",
                        "confidence": 0.9,
                        "source": "research_worker",
                        "implementation_implications": ["Provide create issue capability"],
                    },
                ],
                "recommended_patterns": ["Keep API integration in a service boundary"],
                "dependency_recommendations": ["Read credentials from environment variables"],
            }
        ],
        "architecture_review": {
            "confidence": 0.85,
            "recommendations": ["Use Worker + Service pattern"],
            "preferred_patterns": ["Reuse existing service boundaries"],
            "dependency_guidance": ["Avoid direct API calls from worker"],
            "architecture_approved": True,
        },
        "confidence": {"overall": 0.88, "required": 0.75},
    }


def test_planner_generates_work_packet(monkeypatch):
    monkeypatch.setattr(
        planner_agent,
        "invoke_llm",
        lambda purpose, prompt: fake_llm_response(
            {
                "objective": "Create a new Jira worker agent that can create and comment on tickets.",
                "strategy": "Build governed integration.",
                "steps": [],
            }
        ),
    )

    result = planner_agent.execute_planner_agent(
        task={"title": "Create Jira worker", "description": "create and comment on tickets"},
        discovery_resolution=discovery_payload(),
        known_files=[
            "agents/dev_worker_agent.py",
            "services/research_worker_service.py",
            "tests/test_requirement_trace_service.py",
            "schemas/plan_schema.py",
            "services/requirement_trace_service.py",
        ],
    )

    packet = result["content"]["work_packet"]

    assert result["validation_error"] is None
    assert packet["objective"]
    assert packet["target_files"]
    assert packet["requirements"]
    assert packet["acceptance_criteria"]
    assert packet["test_targets"]
    assert packet["test_commands"]


def test_planner_consumes_research_results(monkeypatch):
    monkeypatch.setattr(
        planner_agent,
        "invoke_llm",
        lambda purpose, prompt: fake_llm_response({"objective": "Create Jira worker", "strategy": "Use evidence.", "steps": []}),
    )

    result = planner_agent.execute_planner_agent(
        task={"title": "Create Jira worker", "description": "Jira Cloud API Token Create Issue Add Comment"},
        discovery_resolution=discovery_payload(),
    )

    packet = result["content"]["work_packet"]

    assert "Use Jira Cloud API token authentication" in packet["implementation_strategy"]
    assert any("create issue" in req.lower() for req in packet["requirements"])
    assert "Jira Cloud supports API token authentication." in packet["discovery_evidence"]["research_claims"]


def test_planner_consumes_architecture_review(monkeypatch):
    monkeypatch.setattr(
        planner_agent,
        "invoke_llm",
        lambda purpose, prompt: fake_llm_response({"objective": "Create Jira worker", "strategy": "Use architecture.", "steps": []}),
    )

    result = planner_agent.execute_planner_agent(
        task={"title": "Create Jira worker", "description": "Jira worker"},
        discovery_resolution=discovery_payload(),
    )

    packet = result["content"]["work_packet"]

    assert "Use Worker + Service pattern" in packet["architecture_constraints"]
    assert "Avoid direct API calls from worker" in packet["architecture_constraints"]


def test_planner_consumes_confidence_state(monkeypatch):
    monkeypatch.setattr(
        planner_agent,
        "invoke_llm",
        lambda purpose, prompt: fake_llm_response({"objective": "Create Jira worker", "strategy": "Use confidence.", "steps": []}),
    )

    result = planner_agent.execute_planner_agent(
        task={"title": "Create Jira worker", "description": "Jira worker"},
        discovery_resolution=discovery_payload(),
    )

    assert result["content"]["work_packet"]["discovery_evidence"]["confidence"]["overall"] == 0.88


def test_new_service_generates_test_file():
    packet = PlannerWorkPacketService().build(
        objective="Create service",
        task={"target_files": ["services/jira_service.py"]},
    )

    assert "services/jira_service.py" in packet.target_files
    assert "tests/test_jira_service.py" in packet.target_files
    assert "tests/test_jira_service.py" in packet.test_targets


def test_new_worker_generates_test_file():
    packet = PlannerWorkPacketService().build(
        objective="Create worker",
        task={"target_files": ["agents/jira_worker_agent.py"]},
    )

    assert "agents/jira_worker_agent.py" in packet.target_files
    assert "tests/test_jira_worker_agent.py" in packet.target_files


def test_planner_expands_target_files():
    service = PlannerWorkPacketService()

    assert service.expand_target_files(["services/jira_service.py"]) == [
        "services/jira_service.py",
        "tests/test_jira_service.py",
    ]


def test_planner_selects_repository_examples():
    service = PlannerWorkPacketService()

    examples = service.select_repository_examples(
        ["services/jira_service.py", "tests/test_jira_service.py"],
        known_files=[
            "services/research_worker_service.py",
            "services/discovery_service.py",
            "tests/test_discovery_service.py",
            "schemas/plan_schema.py",
            "services/requirement_trace_service.py",
        ],
    )

    assert "services/research_worker_service.py" in examples
    assert "tests/test_discovery_service.py" in examples
    assert "schemas/plan_schema.py" in examples


def test_planner_provides_repository_evidence_to_devworker():
    packet = PlannerWorkPacketService().build(
        objective="Create Jira service",
        task={"target_files": ["services/jira_service.py"]},
        known_files=["services/discovery_service.py", "tests/test_discovery_service.py"],
    )

    dev_packet = build_devworker_packet(
        objective=packet.objective,
        target_files=packet.target_files,
        repository_result={"evidence": [{"path": path, "content": "example"} for path in packet.repository_evidence]},
        success_criteria=packet.acceptance_criteria,
    )

    assert dev_packet["repo_evidence"]
    assert dev_packet["success_criteria"] == packet.acceptance_criteria


def test_planner_seeds_requirement_trace():
    packet = PlannerWorkPacketService().build(
        objective="Create Jira worker",
        task={"target_files": ["services/jira_service.py"]},
        discovery_resolution=discovery_payload(),
    )

    assert packet.requirements[0].startswith("REQ-001")
    assert any("deterministic tests" in req.lower() for req in packet.requirements)


def test_requirement_trace_contains_acceptance_criteria():
    packet = PlannerWorkPacketService().build(
        objective="Create Jira worker",
        task={"target_files": ["services/jira_service.py"]},
    )

    assert "Requirement trace covers every seeded requirement" in packet.acceptance_criteria


def test_planner_generates_test_targets():
    packet = PlannerWorkPacketService().build(
        objective="Create Jira worker",
        task={"target_files": ["services/jira_service.py"]},
    )

    assert packet.test_targets == ["tests/test_jira_service.py"]
    assert packet.test_commands == ["PYTHONPATH=. python -m pytest tests/test_jira_service.py"]


def test_runtime_validation_receives_test_targets(monkeypatch):
    captured = {}

    class FakeTestExecutionService:
        def __init__(self, repo_root):
            pass

        def execute(self, test_targets, proposal):
            captured["test_targets"] = test_targets
            from models.test_execution_evidence import TestExecutionResult
            return TestExecutionResult(status="pass")

    monkeypatch.setattr("chair.TestExecutionService", FakeTestExecutionService)

    deliverable = {
        "changes": [
            {"path": "services/jira_service.py", "content": "class JiraService:\n    pass\n"},
            {"path": "tests/test_jira_service.py", "content": "def test_jira_service():\n    assert True\n"},
        ]
    }

    validate_patch_proof_of_delivery(
        deliverable=deliverable,
        devworker_packet={
            "objective": "Create Jira service",
            "target_files": ["services/jira_service.py", "tests/test_jira_service.py"],
            "success_criteria": ["JiraService", "test_jira_service"],
            "test_targets": ["tests/test_jira_service.py"],
            "constraints": {"require_requirement_trace": True},
        },
    )

    assert captured["test_targets"] == ["tests/test_jira_service.py"]


def test_planner_expands_companion_test_files_after_retry():
    quality_result = ProposalQualityResult(
        status="fail",
        violations=[
            ProposalQualityViolation(
                code=ProposalQualityFailureCode.UNAUTHORIZED_FILE_CHANGE,
                message="Proposal changes tests/test_jira_service.py, which is not in target_files.",
                file_path="tests/test_jira_service.py",
                expected="services/jira_service.py",
                actual="tests/test_jira_service.py",
            )
        ],
    )

    packet = expand_devworker_packet_for_companion_tests(
        devworker_packet={"target_files": ["services/jira_service.py"], "constraints": {}},
        quality_result=quality_result,
    )

    assert packet["target_files"] == ["services/jira_service.py", "tests/test_jira_service.py"]
    assert packet["constraints"]["planner_expanded_companion_test_files"] is True


def test_user_feedback_directory_created():
    assert Path(".ageix/user_feedback/.gitkeep").exists()


def test_answer_files_not_committed():
    gitignore = Path(".gitignore").read_text()

    assert ".ageix/user_feedback/*" in gitignore
    assert "!.ageix/user_feedback/.gitkeep" in gitignore


def test_jira_worker_generates_complete_work_packet():
    packet = PlannerWorkPacketService().build(
        objective="Create a new Jira worker agent that can create and comment on tickets.",
        discovery_resolution=discovery_payload(),
        known_files=[
            "agents/dev_worker_agent.py",
            "services/discovery_service.py",
            "tests/test_discovery_service.py",
            "schemas/plan_schema.py",
            "services/requirement_trace_service.py",
        ],
    )

    assert "services/jira_service.py" in packet.target_files
    assert "agents/jira_worker_agent.py" in packet.target_files
    assert packet.test_targets
    assert packet.requirements
    assert packet.repository_evidence


def test_jira_worker_includes_test_targets():
    packet = PlannerWorkPacketService().build(
        objective="Create a new Jira worker agent that can create and comment on tickets.",
    )

    assert "tests/test_jira_service.py" in packet.test_targets
    assert "tests/test_jira_worker_agent.py" in packet.test_targets


def test_jira_worker_includes_requirement_trace():
    packet = PlannerWorkPacketService().build(
        objective="Create a new Jira worker agent that can create and comment on tickets.",
        discovery_resolution=discovery_payload(),
    )

    assert any(req.startswith("REQ-") for req in packet.requirements)
    assert "Requirement trace covers every seeded requirement" in packet.acceptance_criteria


def test_jira_worker_includes_repository_evidence():
    packet = PlannerWorkPacketService().build(
        objective="Create a new Jira worker agent that can create and comment on tickets.",
        known_files=[
            "agents/dev_worker_agent.py",
            "services/discovery_service.py",
            "tests/test_discovery_service.py",
            "schemas/plan_schema.py",
            "services/requirement_trace_service.py",
        ],
    )

    assert packet.repository_evidence


def test_planner_architecture_profile_registered():
    profile = WorkerProfileService().get_profile("planner_implementation_architect")

    assert profile.output_contract == "work_packet"
    assert "work_packet_generation" in profile.capabilities
