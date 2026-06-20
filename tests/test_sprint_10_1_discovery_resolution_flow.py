import json
from pathlib import Path

import pytest

from models.architecture_review import ArchitectureReview
from models.research import ResearchResult
from services.architecture_review_service import ArchitectureReviewService
from services.discovery_artifact_service import DiscoveryArtifactService
from services.discovery_resolution_service import DiscoveryResolutionService
from services.research_worker_service import ResearchWorkerService
from services.worker_profile_service import WorkerProfileService


JIRA_ANSWERS = {
    "jira_platform": "jira_cloud",
    "jira_auth_method": "api_token",
    "integration_use_case": "create_and_comment",
    "dependency_policy": "stdlib_only",
    "config_location": "environment_variables",
}


def test_research_worker_generates_result():
    result = ResearchWorkerService().research(
        objective="Create a new Jira worker agent.",
        research_topics=["Jira Cloud API authentication"],
    )

    assert result.result_type == "research_result"
    assert result.confidence >= 0.75


def test_research_worker_cannot_generate_patch():
    with pytest.raises(ValueError):
        ResearchWorkerService().validate_no_patch({"changes": []})


def test_research_worker_produces_claims():
    result = ResearchWorkerService().research(
        objective="Create a new Jira worker agent.",
        research_topics=["Jira issue creation endpoint"],
    )

    assert result.claims
    assert result.claims[0].source


def test_research_worker_requires_sources_for_claims():
    result = ResearchWorkerService().research(
        objective="Create a new Jira worker agent.",
        research_topics=["Jira comment endpoint"],
    )

    assert all(claim.source for claim in result.claims)


def test_architecture_review_generates_recommendations():
    review = ArchitectureReviewService().review(
        objective="Create a new Jira worker agent.",
        research_results=[ResearchResult(confidence=0.9)],
    )

    assert review.result_type == "architecture_review"
    assert review.recommendations


def test_architecture_review_cannot_generate_patch():
    with pytest.raises(ValueError):
        ArchitectureReviewService().validate_no_patch({"patch_proposal": {}})


def test_architecture_review_can_raise_confidence():
    review = ArchitectureReviewService().review(
        objective="Create a new Jira worker agent.",
        research_results=[ResearchResult(confidence=0.9)],
    )

    assert review.confidence >= 0.85


def test_architecture_review_can_block_planning():
    review = ArchitectureReviewService().review(objective="Create a new Jira API worker agent.")

    assert review.architecture_approved is False
    assert review.confidence < 0.75


def test_discovery_resolves_after_research_and_architecture():
    result = DiscoveryResolutionService().resolve(
        objective="Create a new Jira worker agent that can create and comment on tickets.",
        target_files=["agents/jira_agent.py"],
        answers=JIRA_ANSWERS,
    )

    assert result.status == "ready_for_planning"
    assert result.research_results
    assert result.architecture_review is not None
    assert result.confidence.overall >= result.confidence.required


def test_discovery_remains_blocked_when_research_missing():
    result = DiscoveryResolutionService().resolve(
        objective="Create a new Jira worker agent that can create and comment on tickets.",
        target_files=["agents/jira_agent.py"],
        answers=JIRA_ANSWERS,
        execute_research=False,
    )

    assert result.status == "research_pending"


def test_discovery_remains_blocked_when_architecture_missing():
    result = DiscoveryResolutionService().resolve(
        objective="Create a new Jira worker agent that can create and comment on tickets.",
        target_files=["agents/jira_agent.py"],
        answers=JIRA_ANSWERS,
        execute_architecture_review=False,
    )

    assert result.status == "architecture_pending"


def test_planner_unlocked_after_discovery_resolution():
    result = DiscoveryResolutionService().resolve(
        objective="Create a new Jira worker agent that can create and comment on tickets.",
        target_files=["agents/jira_agent.py"],
        answers=JIRA_ANSWERS,
    )

    assert result.ready


def test_planner_stays_blocked_when_confidence_insufficient():
    result = DiscoveryResolutionService().resolve(
        objective="Create Jira.",
        target_files=[],
        answers={},
    )

    assert not result.ready


def test_discovery_artifacts_persist(tmp_path):
    result = DiscoveryResolutionService(tmp_path).resolve(
        objective="Create a new Jira worker agent that can create and comment on tickets.",
        target_files=["agents/jira_agent.py"],
        answers=JIRA_ANSWERS,
        run_id="run_10_1",
        persist=True,
    )

    run_dir = tmp_path / ".ageix" / "runs" / "run_10_1"
    assert result.ready
    assert (run_dir / "objective.json").exists()
    assert (run_dir / "discovery_packet.json").exists()
    assert (run_dir / "confidence_state.json").exists()


def test_research_result_persisted(tmp_path):
    DiscoveryResolutionService(tmp_path).resolve(
        objective="Create a new Jira worker agent that can create and comment on tickets.",
        target_files=["agents/jira_agent.py"],
        answers=JIRA_ANSWERS,
        run_id="run_10_1",
        persist=True,
    )

    data = json.loads((tmp_path / ".ageix" / "runs" / "run_10_1" / "research_result.json").read_text())
    assert data[0]["result_type"] == "research_result"


def test_architecture_review_persisted(tmp_path):
    DiscoveryResolutionService(tmp_path).resolve(
        objective="Create a new Jira worker agent that can create and comment on tickets.",
        target_files=["agents/jira_agent.py"],
        answers=JIRA_ANSWERS,
        run_id="run_10_1",
        persist=True,
    )

    data = json.loads((tmp_path / ".ageix" / "runs" / "run_10_1" / "architecture_review.json").read_text())
    assert data["result_type"] == "architecture_review"


def test_blocker_lineage_persisted(tmp_path):
    DiscoveryResolutionService(tmp_path).resolve(
        objective="Create a new Jira worker agent that can create and comment on tickets.",
        target_files=["agents/jira_agent.py"],
        answers=JIRA_ANSWERS,
        run_id="run_10_1",
        persist=True,
    )

    data = json.loads((tmp_path / ".ageix" / "runs" / "run_10_1" / "blocker_lineage.json").read_text())
    assert any(item["resolved"] for item in data)


def test_worker_profile_contains_persona_constraints_and_router_hints():
    profile = WorkerProfileService().get_profile("ux_architect")

    assert profile.persona.name
    assert "no_file_writes" in profile.constraints
    assert profile.router_hints


def test_worker_profiles_reference_prompt_files():
    service = WorkerProfileService()

    for profile in service.list_profiles():
        assert Path(profile.prompt_file).exists()


def test_ux_architect_profile_is_defined_but_not_executed():
    profile = WorkerProfileService().get_profile("ux_architect")

    assert profile.worker_id == "ux_architect"
    assert profile.output_contract == "architecture_review"


def test_research_worker_prompt_file_exists():
    assert Path("prompts/research_worker_system.txt").exists()


def test_cloud_architect_prompt_file_exists():
    assert Path("prompts/cloud_architect_system.txt").exists()


def test_ux_architect_prompt_file_exists_for_future_profile():
    assert Path("prompts/ux_architect_system.txt").exists()


def test_utc_timestamp_generation_uses_timezone_aware_datetime():
    timestamp = DiscoveryArtifactService().timestamp()

    assert timestamp.endswith("+00:00")


def test_jira_discovery_to_planning_flow():
    result = DiscoveryResolutionService().resolve(
        objective="Create a new Jira worker agent that can create and comment on tickets.",
        target_files=["agents/jira_agent.py"],
        answers=JIRA_ANSWERS,
    )

    assert result.status == "ready_for_planning"
