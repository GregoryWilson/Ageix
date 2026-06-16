from pathlib import Path

from services.evidence_context_service import EvidenceContextService
from services.planner_work_packet_service import PlannerWorkPacketService
from services.target_resolution_service import TargetResolutionService


def write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "# test\n", encoding="utf-8")


def repo(tmp_path: Path) -> Path:
    write(tmp_path / "router.py")
    write(tmp_path / "planner.py")
    write(tmp_path / "services" / "discovery_service.py")
    write(tmp_path / "services" / "config.py")
    write(tmp_path / "workers" / "config.py")
    write(tmp_path / "tests" / "test_router.py")
    write(tmp_path / "tests" / "test_discovery_service.py")
    return tmp_path


def test_exact_path_resolution(tmp_path):
    root = repo(tmp_path)

    result = TargetResolutionService(root).resolve_targets(["router.py"], persist=False)

    assert result.resolved_targets == ["router.py"]
    assert result.evidence[0].resolution_method == "exact_path"
    assert result.evidence[0].confidence == 1.0


def test_exact_filename_resolution(tmp_path):
    root = repo(tmp_path)

    result = TargetResolutionService(root).resolve_targets(["planner/router.py"], persist=False)

    assert result.resolved_targets == ["router.py"]
    assert result.evidence[0].resolution_method == "exact_filename"
    assert result.evidence[0].confidence >= 0.75


def test_basename_resolution(tmp_path):
    root = repo(tmp_path)

    result = TargetResolutionService(root).resolve_targets(["repository/discovery_service.py"], persist=False)

    assert result.resolved_targets == ["services/discovery_service.py"]
    assert result.evidence[0].resolution_method in {"exact_filename", "basename_match"}


def test_directory_similarity_resolution(tmp_path):
    root = repo(tmp_path)

    evidence = TargetResolutionService(root).resolve_target("service/discovery_service.py")

    assert evidence.resolved_target == "services/discovery_service.py"
    assert "directory_similarity" in evidence.candidate_matches[0].matched_signals or evidence.resolution_method == "exact_filename"


def test_resolution_confidence_scoring(tmp_path):
    root = repo(tmp_path)

    evidence = TargetResolutionService(root).resolve_target("planner/router.py")

    assert evidence.confidence > 0.90
    assert evidence.candidate_matches[0].path == "router.py"
    assert evidence.candidate_matches[0].confidence >= evidence.confidence


def test_resolution_failure_requires_revisit(tmp_path):
    root = repo(tmp_path)

    result = TargetResolutionService(root).resolve_targets(["repository/not_real.py"], persist=False)

    assert result.resolved_targets == []
    assert result.unresolved_targets == ["repository/not_real.py"]
    assert result.planner_revisit_required is True
    assert result.evidence[0].planner_revisit_required is True


def test_unresolved_target_never_reaches_scope(tmp_path):
    root = repo(tmp_path)

    packet = PlannerWorkPacketService(root).build(
        objective="Modify the hallucinated repository target",
        task={"target_files": ["repository/not_real.py"]},
    )

    assert "repository/not_real.py" not in packet.approved_scope
    assert packet.planner_revisit_required is True


def test_scope_contains_only_resolved_targets(tmp_path):
    root = repo(tmp_path)

    packet = PlannerWorkPacketService(root).build(
        objective="Modify router behavior",
        task={"target_files": ["planner/router.py"]},
    )

    assert packet.approved_scope == ["router.py"]
    assert packet.resolved_target_files == ["router.py"]
    assert packet.unresolved_target_files == []


def test_devworker_receives_resolved_targets_only(tmp_path):
    root = repo(tmp_path)
    packet = PlannerWorkPacketService(root).build(
        objective="Modify router behavior",
        task={"target_files": ["planner/router.py"]},
    )

    context = EvidenceContextService(root).build_devworker_context(packet)

    assert context.approved_scope == ["router.py"]
    assert "planner/router.py" not in context.files
    assert "router.py" in context.files


def test_resolution_evidence_generated(tmp_path):
    root = repo(tmp_path)

    packet = PlannerWorkPacketService(root).build(
        objective="Modify router behavior",
        task={"target_files": ["planner/router.py"]},
    )

    assert packet.target_resolution_evidence["evidence"]
    assert packet.target_resolution_evidence["evidence"][0]["requested_target"] == "planner/router.py"


def test_candidate_matches_recorded(tmp_path):
    root = repo(tmp_path)

    evidence = TargetResolutionService(root).resolve_target("config.py")

    assert len(evidence.candidate_matches) >= 2
    assert {candidate.path for candidate in evidence.candidate_matches} >= {"services/config.py", "workers/config.py"}


def test_rejected_candidates_recorded(tmp_path):
    root = repo(tmp_path)

    evidence = TargetResolutionService(root).resolve_target("config.py")

    assert evidence.rejected_candidates
    assert all(candidate.path != evidence.resolved_target for candidate in evidence.rejected_candidates)


def test_minimum_confidence_enforced(tmp_path):
    root = repo(tmp_path)
    controls = root / ".ageix" / "config" / "controls.json"
    controls.parent.mkdir(parents=True)
    controls.write_text('{"target_resolution": {"minimum_confidence": 0.99}}', encoding="utf-8")

    result = TargetResolutionService(root).resolve_targets(["planner/router.py"], persist=False)

    assert result.resolved_targets == []
    assert result.planner_revisit_required is True


def test_planner_revisit_threshold_enforced(tmp_path):
    root = repo(tmp_path)
    controls = root / ".ageix" / "config" / "controls.json"
    controls.parent.mkdir(parents=True)
    controls.write_text('{"target_resolution": {"planner_revisit_threshold": 0.90}}', encoding="utf-8")

    evidence = TargetResolutionService(root).resolve_target("repository/discovery.py")

    assert evidence.planner_revisit_required is True
    assert evidence.candidate_matches == []


def test_planner_target_resolution_pipeline(tmp_path):
    root = repo(tmp_path)

    packet = PlannerWorkPacketService(root).build(
        objective="Modify router behavior",
        planner_data={"target_files": ["planner/router.py"]},
    )

    assert packet.target_files == ["router.py"]
    assert packet.approved_scope == ["router.py"]
    assert packet.planner_revisit_required is False


def test_target_resolution_before_context_generation(tmp_path):
    root = repo(tmp_path)

    packet = PlannerWorkPacketService(root).build(
        objective="Modify router behavior",
        task={"target_files": ["planner/router.py"]},
    )
    context = EvidenceContextService(root).build_devworker_context(packet)

    assert list(context.files) == ["router.py"]


def test_grounded_targets_reduce_hallucinated_files(tmp_path):
    root = repo(tmp_path)

    packet = PlannerWorkPacketService(root).build(
        objective="Modify router and discovery behavior",
        task={"target_files": ["planner/router.py", "repository/not_real.py"]},
    )

    assert "router.py" in packet.approved_scope
    assert "planner/router.py" not in packet.approved_scope
    assert "repository/not_real.py" not in packet.approved_scope
    assert packet.planner_revisit_required is True



def test_add_validation_tests_does_not_forgive_unresolved_planner_targets(tmp_path):
    root = repo(tmp_path)

    packet = PlannerWorkPacketService(root).build(
        objective="Update config handling logic for worker configuration and add validation tests",
        planner_data={
            "target_files": [
                "config/worker_config.py",
                "services/config_service.py",
                "validators/config_validator.py",
                "tests/test_worker_config.py",
                "tests/test_config_validator.py",
            ]
        },
    )

    assert packet.planner_revisit_required is True
    assert packet.approved_scope == []
    assert packet.resolved_target_files == []
    assert packet.unresolved_target_files == [
        "config/worker_config.py",
        "services/config_service.py",
        "validators/config_validator.py",
        "tests/test_worker_config.py",
        "tests/test_config_validator.py",
    ]


def test_creation_intent_requires_stronger_create_signal_than_add(tmp_path):
    root = repo(tmp_path)
    service = PlannerWorkPacketService(root)

    assert service._objective_intends_creation("Update config handling and add validation tests") is False
    assert service._objective_intends_creation("Create a new Jira worker agent") is True


def test_chair_blocks_devworker_when_planner_revisit_required(monkeypatch):
    from chair import execute_ready_step

    dispatched_agents = []

    def fake_dispatch_agent(agent_name, payload):
        dispatched_agents.append(agent_name)
        return {"deliverable": {"result_type": "patch_proposal"}}

    monkeypatch.setattr("chair.dispatch_agent", fake_dispatch_agent)

    state = {
        "plan": {
            "work_packet": {
                "planner_revisit_required": True,
                "unresolved_target_files": ["config/worker_config.py"],
                "target_resolution_evidence": {
                    "planner_revisit_required": True,
                    "unresolved_targets": ["config/worker_config.py"],
                    "evidence": [
                        {
                            "requested_target": "config/worker_config.py",
                            "resolved_target": None,
                            "resolution_method": "planner_revisit_required",
                            "planner_revisit_required": True,
                            "candidate_matches": [],
                        }
                    ],
                },
            },
            "steps": [
                {
                    "id": "step_1",
                    "agent": "dev_worker",
                    "objective": "Update config handling and add validation tests",
                    "target_files": ["config/worker_config.py"],
                    "constraints": {"allow_create_files": True},
                    "dependencies": [],
                    "status": "pending",
                }
            ],
        },
        "agent_turns": [],
    }

    result = execute_ready_step(state)

    assert dispatched_agents == []
    assert result["status"] == "blocked"
    assert result["chair_action"] == "target_resolution_failed"
    assert result["context_request"]["reason"] == "target_resolution_failed"
    assert result["context_request"]["recommended_planner_revisit"] is True
    assert result["plan"]["steps"][0]["status"] == "blocked"
