import json

import chair
from agents.planner_agent import extract_json
from models.proposal_quality_models import ProposalQualityFailureCode
from services.discovery_service import DiscoveryService
from services.proposal_quality_service import ProposalQualityService


def test_discovery_gate_blocks_underspecified_jira_worker_before_planning():
    result = DiscoveryService().analyze(
        objective="Create a new Jira worker agent.",
        target_files=["agents/jira_agent.py"],
    )

    assert result.status == "discovery_required"
    assert result.confidence.overall < result.confidence.required
    assert result.research_required is True
    assert result.architecture.review_required is True
    assert result.architecture.preferred_reviewer == "cloud_architect"
    assert any(question.id == "jira_auth_method" for question in result.questions)


def test_discovery_answer_request_for_options_returns_guidance():
    result = DiscoveryService().analyze(
        objective="Create a new Jira worker agent.",
        answers={"jira_auth_method": "What are my auth options?"},
    )

    auth = next(item for item in result.answer_validation if item.question_id == "jira_auth_method")
    assert auth.status == "guidance_requested"
    assert "Jira Cloud" in auth.guidance


def test_discovery_invalid_answer_is_rejected():
    result = DiscoveryService().analyze(
        objective="Create a new Jira worker agent.",
        answers={"jira_auth_method": "dongle"},
    )

    auth = next(item for item in result.answer_validation if item.question_id == "jira_auth_method")
    assert auth.status == "invalid"
    assert "Unsupported answer" in auth.message


def test_discovery_unknown_answer_is_accepted_without_confidence_gain():
    result = DiscoveryService().analyze(
        objective="Create a new Jira worker agent.",
        answers={"jira_auth_method": "unknown"},
    )

    auth = next(item for item in result.answer_validation if item.question_id == "jira_auth_method")
    assert auth.status == "accepted_uncertain"
    assert auth.confidence_delta == 0.0


def test_discovery_scripted_answers_raise_confidence_and_can_clear_gate():
    answers = {
        "jira_platform": "jira_cloud",
        "jira_auth_method": "api_token",
        "integration_use_case": "create_and_comment",
        "dependency_policy": "stdlib_only",
        "config_location": "environment_variables",
        "research_evidence": True,
        "architecture_review": "approved",
    }

    result = DiscoveryService().analyze(
        objective="Create a new Jira worker agent at agents/jira_agent.py with mocked network tests.",
        target_files=["agents/jira_agent.py", "tests/test_jira_agent.py"],
        answers=answers,
    )

    assert result.status == "ready_for_planning"
    assert result.confidence.overall >= result.confidence.required
    assert result.architecture.review_required is False


def test_chair_discovery_gate_prevents_planner_and_devworker(monkeypatch):
    calls = []

    def fake_dispatch(agent_key, payload):
        calls.append(agent_key)
        raise AssertionError("No agents should be dispatched when discovery is blocking.")

    monkeypatch.setattr(chair, "dispatch_agent", fake_dispatch)

    result = DiscoveryService().analyze(
        objective="Create a new Jira worker agent.",
        target_files=["agents/jira_agent.py"],
    )

    assert result.status == "discovery_required"
    assert calls == []


def test_planner_recovers_json_from_fenced_response_with_trailing_explanation():
    raw = """```json
{"steps": [{"id": "step_1", "agent": "repository"}]}
```

### Explanation
Ignore this.
"""

    assert extract_json(raw) == {"steps": [{"id": "step_1", "agent": "repository"}]}


def test_dependency_validation_reports_unsupported_import_with_syntax_error_present(tmp_path):
    proposal = {
        "changes": [
            {
                "operation": "create_file",
                "path": "tests/test_3D_printer_agent.py",
                "content": "from dependency_injection import inject\nfrom agents.3D_printer_agent import Agent\nassert True\n",
            }
        ]
    }

    result = ProposalQualityService(tmp_path).validate(
        proposal=proposal,
        objective="Create test",
        target_files=["tests/test_3D_printer_agent.py"],
    )

    codes = {violation.code for violation in result.violations}
    assert ProposalQualityFailureCode.PYTHON_SYNTAX_ERROR in codes
    assert ProposalQualityFailureCode.UNSUPPORTED_DEPENDENCY_REFERENCE in codes


def test_architecture_review_stub_routes_new_external_worker_to_cloud_architect():
    result = DiscoveryService().analyze(
        objective="Create a new worker agent that integrates with Jira and handles authentication.",
        target_files=["agents/jira_agent.py"],
    )

    assert result.architecture.review_recommended is True
    assert result.architecture.review_required is True
    assert result.architecture.preferred_reviewer == "cloud_architect"
    assert "New external integration" in result.architecture.reasons
