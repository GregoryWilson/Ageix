import json
from typing import Any
import copy
from agents.dispatcher import dispatch_agent
from work_order_runner import run_work_order
from pathlib import Path
from services.staging_service import StagingService
from contracts.patch_contract import PatchProposal
from services.patch_builder import PatchBuilder
import argparse
from services.objective_source_service import ObjectiveSourceService
from services.proposal_quality_service import ProposalQualityService
from services.behavioral_smoke_verifier import BehavioralSmokeVerifier
from services.requirement_trace_service import RequirementTraceService
from services.validation_evidence_service import ValidationEvidenceService
from services.test_execution_service import TestExecutionService
from services.confidence_scoring_service import ConfidenceScoringService
from services.promotion_readiness_service import PromotionReadinessService
from services.governance_review_packet_service import GovernanceReviewPacketService
from services.discovery_service import DiscoveryService
from services.discovery_resolution_service import DiscoveryResolutionService
from services.planner_work_packet_service import PlannerWorkPacketService
from services.patch_proposal_contract_service import PatchProposalContractService
from models.test_execution_evidence import TestExecutionResult

MAX_PROPOSAL_QUALITY_RETRIES = 1

def build_chair_message(status: dict) -> str:
    title = status["title"]
    task_status = status["status"]
    progress = status["progress"]
    next_actions = status.get("next_actions", [])

    total = progress.get("total", 0)
    completed = progress.get("completed", 0)
    in_progress = progress.get("in_progress", 0)
    blocked = progress.get("blocked", 0)
    new = progress.get("new", 0)

    message = (
        f"Task '{title}' is currently {task_status}. "
        f"Progress is {completed}/{total} child tasks complete. "
    )

    if blocked:
        message += f"There are {blocked} blocked tasks that need attention. "
    elif in_progress:
        message += f"There are {in_progress} tasks currently in progress. "
    elif new:
        message += f"There are {new} tasks ready to start. "

    if next_actions:
        message += f"Recommended next action: {next_actions[0]}."

    return message


def build_agent_turn_summary(turns: list[dict]) -> str:
    if not turns:
        return "No agent turns have been recorded yet."

    visible = [t for t in turns if t.get("visibility") in ("internal", "public")]

    if not visible:
        return "No visible agent activity has been recorded."

    latest = visible[-3:]

    parts = []
    for turn in latest:
        parts.append(
            f"{turn['agent_name']} recorded a {turn['turn_type']}: {turn['content']}"
        )

    return " ".join(parts)


def build_plan_for_task(
    task: dict,
    parent_task: dict | None = None,
    sibling_tasks: list[dict] | None = None,
    conversation_summary: str = "",
    recent_messages: list[dict] | None = None,
    task_events: list[dict] | None = None,
    known_files: list[str] | None = None,
    discovery_resolution: dict | None = None,
) -> dict:
    planner_turn = dispatch_agent(
        "planner",
        {
            "task": task,
            "parent_task": parent_task,
            "sibling_tasks": sibling_tasks,
            "conversation_summary": conversation_summary,
            "recent_messages": recent_messages,
            "task_events": task_events,
            "known_files": known_files,
            "discovery_resolution": discovery_resolution,
        },
    )

    plan = copy.deepcopy(planner_turn.get("content", {}))
    
    return {
        "chair_action": "plan_created",
        "planner_turn": planner_turn,
        "plan": plan,
        "plan_step_count": len(plan.get("steps", [])),
        "validation_error": planner_turn.get("validation_error"),
    }

def create_chair_state(
    task: dict,
    plan_result: dict,
) -> dict:
    plan = initialize_plan_steps(plan_result.get("plan", {}))

    return {
        "task": task,
        "status": "planned",
        "plan": plan,
        "planner_turn": plan_result.get("planner_turn", {}),
        "plan_step_count": plan_result.get("plan_step_count", 0),
        "validation_error": plan_result.get("validation_error"),
        "agent_turns": [
            plan_result.get("planner_turn", {})
        ],
    }

def get_completed_step_ids(state: dict[str, Any]) -> set[str]:
    steps = state.get("plan", {}).get("steps", [])

    return {
        step["id"]
        for step in steps
        if step.get("status") == "completed"
    }


def dependencies_satisfied(
    step: dict[str, Any],
    completed_step_ids: set[str],
) -> bool:
    dependencies = step.get("dependencies", [])

    return all(dep in completed_step_ids for dep in dependencies)


def get_ready_steps(state: dict[str, Any]) -> list[dict[str, Any]]:
    steps = state.get("plan", {}).get("steps", [])
    completed_step_ids = get_completed_step_ids(state)

    ready_steps = []

    for step in steps:
        if step.get("status", "pending") != "pending":
            continue

        if dependencies_satisfied(step, completed_step_ids):
            ready_steps.append(step)

    return ready_steps


def build_step_payload(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "objective": step.get("objective", ""),
        "instructions": step.get("instructions", ""),
        "constraints": step.get("constraints", {}),
        "expected_output": step.get("expected_output", {}),
    }

def normalize_agent_key(agent_name: str) -> str:
    normalized = (
        agent_name
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )

    aliases = {
        "researchagent": "research",
        "research_agent": "research",
        "research": "research",

        "planneragent": "planner",
        "planner_agent": "planner",
        "planner": "planner",

        "comparisonagent": "comparison",
        "comparison_agent": "comparison",
        "comparison": "comparison",

        "recommendationagent": "recommendation",
        "recommendation_agent": "recommendation",
        "recommendation": "recommendation",

        "devworkeragent": "dev_worker",
        "dev_worker_agent": "dev_worker",
        "devworker": "dev_worker",
        "dev_worker": "dev_worker",
        "developer": "dev_worker",
        "worker": "dev_worker",

        "repositoryagent": "repository",
        "repository_agent": "repository",
        "repository": "repository",
        "repo": "repository",

        "cloudarchitect": "cloud_architect",
        "cloud_architect": "cloud_architect",
        "cloud_architect_agent": "cloud_architect",
    }

    return aliases.get(normalized, normalized)

def dispatch_packet_to_agent(agent_key: str):
    def _runner(packet: dict) -> dict:
        return dispatch_agent(
            agent_key=agent_key,
            payload=packet,
        )

    return _runner


def build_agent_registry() -> dict:
    agent_keys = [
        "research",
        "comparison",
        "recommendation",
        "planner",
        "dev_worker",
        "repository",
        "cloud_architect",
    ]

    return {
        key: dispatch_packet_to_agent(key)
        for key in agent_keys
    }


def execute_ready_step(state: dict[str, Any], max_context_expansions: int = 1,
    context_expansion_count: int = 0,) -> dict[str, Any]:
  
    ready_steps = get_ready_steps(state)

    if not ready_steps:
        state["chair_action"] = "no_ready_steps"
        return update_plan_status(state)

    step = ready_steps[0]
    agent_key = normalize_agent_key(step.get("agent", "research"))

    step["status"] = "in_progress"
    work_packet = state.get("plan", {}).get("work_packet") or {}

    try:
        if agent_key == "dev_worker":
            if work_packet.get("planner_revisit_required"):
                unresolved_targets = work_packet.get("unresolved_target_files", [])
                resolution_evidence = work_packet.get("target_resolution_evidence", {})
                context_request = {
                    "result_type": "context_request",
                    "reason": "target_resolution_failed",
                    "requested_target": unresolved_targets[0] if unresolved_targets else None,
                    "unresolved_target_files": unresolved_targets,
                    "target_resolution_evidence": resolution_evidence,
                    "recommended_planner_revisit": True,
                }

                step["status"] = "blocked"
                step["block_reason"] = "target_resolution_failed"
                step["result"] = {
                    "status": "blocked",
                    "deliverable": context_request,
                }

                state.setdefault("agent_turns", []).append(
                    {
                        "agent_name": "chair",
                        "turn_type": "blocked",
                        "content": {
                            "step_id": step.get("id"),
                            "agent_key": agent_key,
                            "reason": "target_resolution_failed",
                            "unresolved_target_files": unresolved_targets,
                        },
                        "visibility": "internal",
                    }
                )

                state["chair_action"] = "target_resolution_failed"
                state["context_request"] = context_request
                state["blocked_step_id"] = step.get("id")
                return update_plan_status(state)

            agent_result: dict[str, Any] = {}
            devworker_packet: dict[str, Any] = {}

            for expansion_attempt in range(max_context_expansions + 1):
                repository_result = dispatch_agent(
                    "repository",
                    {
                        "objective": step.get("objective", ""),
                        "instructions": step.get("instructions", ""),
                        "target_files": step.get("target_files", []) or work_packet.get("target_files", []),
                        "requested_operation": "create_file" if step.get("constraints", {}).get("allow_create_files") else "replace_file",
                        "constraints": step.get("constraints", {}),
                        "mode": "evidence_gathering",
                        "include_dependency_hints": True,
                    },
                )

                repository_content = repository_result.get("content", repository_result)

                devworker_packet = build_devworker_packet(
                    objective=step.get("objective", ""),
                    target_files=step.get("target_files", []) or work_packet.get("target_files", []),
                    repository_result=repository_content,
                    step_constraints=step.get("constraints", {}),
                    success_criteria=step.get("success_criteria", []),
                )

                devworker_packet["instructions"] = step.get("instructions", "")
                devworker_packet["expected_output"] = step.get("expected_output", {})
                if work_packet:
                    devworker_packet["work_packet"] = work_packet
                    devworker_packet["success_criteria"] = work_packet.get("acceptance_criteria", step.get("success_criteria", []))
                    devworker_packet["requirements"] = work_packet.get("requirements", [])
                    devworker_packet["test_targets"] = work_packet.get("test_targets", [])
                    devworker_packet["test_commands"] = work_packet.get("test_commands", [])
                    devworker_packet["architecture_constraints"] = work_packet.get("architecture_constraints", [])
                else:
                    devworker_packet["success_criteria"] = step.get("success_criteria", [])

                print(
                    "[Chair] DevWorker packet repo evidence count:",
                    len(devworker_packet.get("repo_evidence", [])),
                    flush=True,
                )

                print(
                   "[Chair] DevWorker constraints:",
                    json.dumps(devworker_packet.get("constraints", {}), indent=2),
                    flush=True,
                )

                agent_result = dispatch_agent("dev_worker", devworker_packet)
                deliverable = agent_result.get("deliverable", {})

                if deliverable.get("result_type") != "context_request":
                    break

                if expansion_attempt >= max_context_expansions:
                    return {
                        "chair_action": "context_request_unresolved",
                        "status": "blocked",
                        "context_request": deliverable,
                        "executed_count": expansion_attempt + 1,
                    }

                requested_files = filter_context_requested_files(
                    deliverable.get("requested_files", []),
                    devworker_packet.get("repo_evidence", []),
                    devworker_packet.get("constraints", {}),
                )

                if not requested_files:
                    return {
                        "chair_action": "create_file_target_context_loop",
                        "status": "blocked",
                        "context_request": deliverable,
                        "retry_feedback": "Do not request contents for a missing file when the requested operation is create_file.",
                    }

                step["target_files"] = sorted(
                    set(step.get("target_files", [])) | set(requested_files)
                )

            deliverable = agent_result.get("deliverable", {})

            if deliverable.get("result_type") == "patch_proposal":
                deliverable = normalize_patch_proposal_deliverable(deliverable)
                agent_result["deliverable"] = deliverable
                print(
                    "[Chair] DevWorker deliverable:",
                    json.dumps(deliverable, indent=2),
                    flush=True,
                )
                validate_patch_proposal_deliverable(deliverable)

                quality_result = validate_patch_proposal_quality(
                    deliverable=deliverable,
                    devworker_packet=devworker_packet,
                )

                if not quality_result.passed:
                    expanded_packet = expand_devworker_packet_for_companion_tests(
                        devworker_packet=devworker_packet,
                        quality_result=quality_result,
                    )
                    if expanded_packet is not devworker_packet:
                        devworker_packet = expanded_packet
                        quality_result = validate_patch_proposal_quality(
                            deliverable=deliverable,
                            devworker_packet=devworker_packet,
                        )

                if not quality_result.passed:
                    retry_packet = build_quality_retry_packet(
                        devworker_packet=devworker_packet,
                        quality_result=quality_result,
                    )

                    agent_result = dispatch_agent("dev_worker", retry_packet)
                    deliverable = agent_result.get("deliverable", {})

                    if deliverable.get("result_type") != "patch_proposal":
                        validate_devworker_deliverable(deliverable)
                    else:
                        deliverable = normalize_patch_proposal_deliverable(deliverable, retry_count=1)
                        agent_result["deliverable"] = deliverable
                        validate_patch_proposal_deliverable(deliverable)
                        quality_result = validate_patch_proposal_quality(
                            deliverable=deliverable,
                            devworker_packet=retry_packet,
                        )

                    if not quality_result.passed:
                        return {
                            "chair_action": "patch_proposal_quality_rejected",
                            "status": "rejected",
                            "errors": [
                                violation.message
                                for violation in quality_result.violations
                            ],
                            "quality_result": quality_result.model_dump(),
                            "patch_proposal": deliverable,
                        }

                trace_result, behavior_result, runtime_result, validation_result = validate_patch_proof_of_delivery(
                    deliverable=deliverable,
                    devworker_packet=devworker_packet,
                )

                if not trace_result.passed or not behavior_result.passed or not runtime_result.passed or not validation_result.passed:
                    retry_packet = build_delivery_retry_packet(
                        devworker_packet=devworker_packet,
                        trace_result=trace_result,
                        behavior_result=behavior_result,
                        runtime_result=runtime_result,
                        validation_result=validation_result,
                    )

                    agent_result = dispatch_agent("dev_worker", retry_packet)
                    deliverable = agent_result.get("deliverable", {})

                    if deliverable.get("result_type") != "patch_proposal":
                        validate_devworker_deliverable(deliverable)
                    else:
                        deliverable = normalize_patch_proposal_deliverable(deliverable, retry_count=1)
                        agent_result["deliverable"] = deliverable
                        validate_patch_proposal_deliverable(deliverable)
                        quality_result = validate_patch_proposal_quality(
                            deliverable=deliverable,
                            devworker_packet=retry_packet,
                        )
                        trace_result, behavior_result, runtime_result, validation_result = validate_patch_proof_of_delivery(
                            deliverable=deliverable,
                            devworker_packet=retry_packet,
                        )

                    if (
                        not quality_result.passed
                        or not trace_result.passed
                        or not behavior_result.passed
                        or not runtime_result.passed
                        or not validation_result.passed
                    ):
                        delivery_violations = build_delivery_feedback_result(
                            trace_result,
                            behavior_result,
                            runtime_result,
                            validation_result,
                        )
                        return {
                            "chair_action": "patch_proposal_quality_rejected",
                            "status": "rejected",
                            "errors": [
                                violation.message
                                for violation in [*quality_result.violations, *delivery_violations]
                            ],
                            "quality_result": quality_result.model_dump(),
                            "requirement_trace_result": trace_result.model_dump(),
                            "behavior_verification_result": behavior_result.model_dump(),
                            "runtime_validation_result": runtime_result.model_dump(),
                            "validation_evidence_result": validation_result.model_dump(),
                            "patch_proposal": deliverable,
                        }


                errors = validate_replace_file_evidence(
                    deliverable,
                    {
                        "evidence": devworker_packet.get("repo_evidence", []),
                    },
                )

                if errors:
                    return {
                        "chair_action": "patch_proposal_rejected",
                        "status": "rejected",
                        "errors": errors,
                        "patch_proposal": deliverable,
                    }

                requirement_trace_summary = RequirementTraceService().summarize(trace_result)
                validation_summary = ValidationEvidenceService().summarize(validation_result)
                runtime_validation_summary = TestExecutionService(Path(".")).summarize(runtime_result)
                confidence_summary = build_confidence_summary(
                    quality_result=quality_result,
                    trace_result=trace_result,
                    behavior_result=behavior_result,
                    validation_result=validation_result,
                    runtime_result=runtime_result,
                )
                promotion_readiness = build_promotion_readiness(
                    quality_result=quality_result,
                    trace_result=trace_result,
                    behavior_result=behavior_result,
                    validation_result=validation_result,
                    runtime_result=runtime_result,
                    confidence_summary=confidence_summary,
                )
                promotion_readiness_summary = PromotionReadinessService(Path(".")).summarize(promotion_readiness)

                if not promotion_readiness.passed:
                    promotion_violations = [
                        blocker.model_dump()
                        for blocker in promotion_readiness.blockers
                    ]
                    return {
                        "chair_action": "patch_promotion_readiness_rejected",
                        "status": "rejected",
                        "errors": [
                            blocker.message
                            for blocker in promotion_readiness.blockers
                        ],
                        "promotion_readiness_result": promotion_readiness.model_dump(),
                        "promotion_retry_packet": build_promotion_retry_packet(
                            devworker_packet=devworker_packet,
                            promotion_readiness=promotion_readiness,
                        ),
                        "quality_result": quality_result.model_dump(),
                        "requirement_trace_result": trace_result.model_dump(),
                        "behavior_verification_result": behavior_result.model_dump(),
                        "runtime_validation_result": runtime_result.model_dump(),
                        "validation_evidence_result": validation_result.model_dump(),
                        "patch_proposal": deliverable,
                    }

                governance_packet = GovernanceReviewPacketService().build_packet(
                    objective=deliverable.get("objective", ""),
                    implementation_summary=deliverable.get("summary", ""),
                    changed_files=[
                        change.get("path", "")
                        for change in deliverable.get("changes", [])
                        if change.get("path")
                    ],
                    requirement_trace=requirement_trace_summary,
                    behavior_verification=behavior_result.model_dump(),
                    validation_evidence=validation_result.model_dump(),
                    runtime_evidence=runtime_result.model_dump(),
                    confidence_summary=confidence_summary,
                    promotion_readiness=promotion_readiness,
                )

                manifest = PatchBuilder(Path(".")).stage_patch_from_deliverable(
                    deliverable,
                    proposal_quality=quality_result.model_dump(),
                    requirement_trace=requirement_trace_summary,
                    behavior_verification=behavior_result.model_dump(),
                    validation_summary=validation_summary,
                    validation_evidence=validation_result.model_dump(),
                    runtime_validation_summary=runtime_validation_summary,
                    runtime_execution_evidence=runtime_result.model_dump(),
                    confidence_summary=confidence_summary,
                    promotion_readiness_summary=promotion_readiness_summary,
                    governance_review_packet=GovernanceReviewPacketService().metadata(governance_packet),
                )

                agent_result["stage_manifest"] = manifest
                agent_result["patch_id"] = manifest["patch_id"]
                agent_result["staged_patch"] = manifest
                agent_result["changed_files"] = manifest["changed_files"]

            else:
                validate_devworker_deliverable(deliverable)

        else:
            prior_artifact_ids = [
                completed_step.get("artifact_id")
                for completed_step in state.get("plan", {}).get("steps", [])
                if completed_step.get("status") == "completed"
                and completed_step.get("artifact_id")
            ]

            work_order = step_to_work_order(
                step=step,
                prior_artifact_ids=prior_artifact_ids,
            )

            agent_result = run_work_order(
                work_order=work_order,
                agent_registry=build_agent_registry(),
            )
    except ValueError as err:
        step["status"] = "blocked"
        step["block_reason"] = str(err)

        state.setdefault("agent_turns", []).append(
            {
                "agent_name": "chair",
                "turn_type": "blocked",
                "content": {
                    "step_id": step.get("id"),
                    "agent_key": agent_key,
                    "reason": str(err),
                },
                "visibility": "internal",
            }
        )

        state["chair_action"] = "step_blocked"
        state["blocked_step_id"] = step.get("id")
        return update_plan_status(state)

    step["status"] = agent_result.get("status", "completed")
    step["result"] = agent_result
    step["artifact_id"] = agent_result.get("artifact_id")
    step["evaluation"] = agent_result.get("evaluation")

    state.setdefault("agent_turns", []).append(
        {
            "agent_name": agent_key,
            "turn_type": "execution",
            "content": agent_result,
            "visibility": "internal",
        }
    )

    state["chair_action"] = "step_executed"
    state["executed_step_id"] = step.get("id")

    return update_plan_status(state)


def update_plan_status(state: dict[str, Any]) -> dict[str, Any]:
    steps = state.get("plan", {}).get("steps", [])

    if not steps:
        state["status"] = "no_plan"
        return state

    statuses = [step.get("status", "pending") for step in steps]

    if any(status == "blocked" for status in statuses):
        state["status"] = "blocked"
    elif all(status == "completed" for status in statuses):
        state["status"] = "completed"
    elif any(status in ("completed", "in_progress") for status in statuses):
        state["status"] = "in_progress"
    else:
        state["status"] = "planned"

    return state

def initialize_plan_steps(plan: dict[str, Any]) -> dict[str, Any]:
    for step in plan.get("steps", []):
        step.setdefault("status", "pending")
        step.setdefault("dependencies", [])
    return plan

def execute_ready_steps_until_blocked_or_done(
    state: dict[str, Any],
    max_steps: int = 10,
) -> dict[str, Any]:
    executed_count = 0

    while executed_count < max_steps:
        ready_steps = get_ready_steps(state)

        if not ready_steps:
            state["chair_action"] = "no_ready_steps"
            break

        previous_action = state.get("chair_action")

        state = execute_ready_step(state)
        executed_count += 1

        if state.get("chair_action") == "step_blocked":
            break

        if state.get("status") == "completed":
            break

        if state.get("chair_action") == previous_action and not get_ready_steps(state):
            break

    state["executed_count"] = executed_count
    return update_plan_status(state)


from work_order import WorkOrder


def step_to_work_order(step: dict, prior_artifact_ids: list[str]) -> WorkOrder:
    expected_output = step.get("expected_output", {})

    deliverable_type = expected_output.get("type", "agent_deliverable")
    required_sections = expected_output.get("required_sections", [])

    if not required_sections:
        required_sections = [
            "summary",
            "findings",
            "risks",
            "assumptions",
        ]

    return WorkOrder(
        work_order_id=step.get("id", "work_order"),
        agent=normalize_agent_key(
            step.get("agent", "unknown_agent")
        ),
        objective=step.get("objective", ""),
        instructions=[
            step.get("instructions", ""),
        ],
        input_artifacts=prior_artifact_ids,
        deliverable={
            "type": deliverable_type,
            "required_sections": required_sections,
        },
        success_criteria=step.get(
            "success_criteria",
            [f"Includes {section}" for section in required_sections],
        ),
        constraints=step.get("constraints", {}),
    )

def build_devworker_packet(
    *,
    objective: str,
    target_files: list[str],
    repository_result: dict,
    step_constraints: dict[str, Any] | None = None,
    success_criteria: list[str] | None = None,
) -> dict:
    repo_evidence = repository_result.get("evidence", [])


    constraints = {
        "proposal_only": True,
        "no_file_writes": True,
        "must_use_repository_evidence": True,
        "must_cite_lines_when_available": True,
        "allowed_operations": ["replace_file"],
    }

    constraints.update(step_constraints or {})

    if constraints.get("allow_create_files"):
        constraints["allowed_operations"] = sorted(
            set(constraints.get("allowed_operations", []))
            | {"replace_file", "create_file"}
        )

    constraints["proposal_only"] = True
    constraints["no_file_writes"] = True

    if not repo_evidence:
        repo_evidence = [
            compact_repo_evidence(item)
            for item in repository_result.get("read_files", [])
        ]

    return {
        "objective": objective,
        "target_files": target_files,
        "success_criteria": success_criteria or [],
        "test_targets": [],
        "test_commands": [],
        "requirements": [],
        "repo_evidence": repo_evidence,
        "dependency_hints": repository_result.get("dependency_hints", []),
        "repository_discovery": {
            "requested_operation": repository_result.get("requested_operation"),
            "missing_allowed_for_create": [
                item.get("path")
                for item in repo_evidence
                if item.get("repository_evidence_status") == "missing_allowed_for_create"
            ],
        },
        "constraints": constraints,
    }

def validate_devworker_result(result: dict[str, Any]) -> None:
    if result.get("agent") != "devworker":
        raise ValueError("DevWorker result must identify agent='devworker'.")

    if result.get("mode") != "proposal_only":
        raise ValueError("DevWorker must run in proposal_only mode.")

    if result.get("no_write_confirmation") is not True:
        raise ValueError("DevWorker must confirm no writes were performed.")

    required_keys = [
        "files_considered",
        "evidence_used",
        "dependency_hints_used",
        "assumptions",
        "dependency_risks",
        "proposed_changes",
        "test_plan",
    ]

    missing = [key for key in required_keys if key not in result]

    if missing:
        raise ValueError(
            f"DevWorker result missing required fields: {missing}"
        )

def validate_devworker_deliverable(deliverable: dict[str, Any]) -> None:
    required = [
        "agent",
        "mode",
        "objective",
        "files_considered",
        "evidence_used",
        "dependency_hints_used",
        "assumptions",
        "dependency_risks",
        "proposed_changes",
        "test_plan",
        "no_write_confirmation",
    ]

    missing = [key for key in required if key not in deliverable]

    if missing:
        raise ValueError(f"DevWorker deliverable missing fields: {missing}")

    if deliverable["agent"] != "devworker":
        raise ValueError("DevWorker deliverable must use agent='devworker'.")

    if deliverable["mode"] != "proposal_only":
        raise ValueError("DevWorker must remain in proposal_only mode.")

    if deliverable["no_write_confirmation"] is not True:
        raise ValueError("DevWorker must confirm no writes.")
    
def normalize_patch_proposal_deliverable(
    deliverable: dict[str, Any],
    *,
    retry_count: int = 0,
) -> dict[str, Any]:
    normalized, _evidence = PatchProposalContractService().normalize(
        deliverable,
        source_agent=deliverable.get("agent") or "devworker",
        retry_count=retry_count,
    )
    return normalized


def validate_patch_proposal_deliverable(
    deliverable: dict[str, Any],
    *,
    approved_scope: list[str] | None = None,
) -> None:

    if deliverable.get("result_type") == "context_request":
        if deliverable.get("reason") != "architecture_scope_exceeded":
            raise ValueError("Unsupported context request reason.")
        if deliverable.get("recommended_planner_revisit") is not True:
            raise ValueError("Scope context request must recommend planner revisit.")
        return

    service = PatchProposalContractService()
    required = PatchProposalContractService.REQUIRED_FIELDS

    forbidden = [
        "<new file content",
        "<placeholder",
        "based on project identity layer requirements",
    ]

    missing = [
        key
        for key in required
        if key not in deliverable
    ]

    if missing:
        failure_code = "missing_changes_field" if "changes" in missing else "missing_required_field"
        raise ValueError(
            f"{failure_code}: Patch proposal missing fields: {missing}"
        )

    if not isinstance(deliverable.get("changes"), list) or not deliverable.get("changes"):
        raise ValueError("empty_patch_proposal: Patch proposal must include at least one change.")

    service.validate_approved_scope(deliverable, approved_scope=approved_scope)

    seen_paths: set[str] = set()

    for change in deliverable["changes"]:
        path = change.get("path")
        operation = change.get("operation")
        content = change.get("content")

        if isinstance(content, str):
            for marker in forbidden:
                if marker.lower() in content.lower():
                    raise ValueError(
                        f"{path} contains placeholder content."
                    )

        if operation not in {"replace_file", "create_file"}:
            raise ValueError(
                f"invalid_patch_operation: Unsupported patch proposal operation: {operation}"
            )

        if not isinstance(path, str) or not path.strip():
            raise ValueError("Patch proposal change missing path.")

        if path.startswith("/") or ".." in path.split("/"):
            raise ValueError(f"Unsafe patch proposal path: {path}")

        if path in seen_paths:
            raise ValueError(f"Duplicate change proposed for {path}")

        seen_paths.add(path)

        if not isinstance(content, str):
            raise ValueError(f"{path} patch content must be a string.")

        if not content.strip():
            raise ValueError(f"{path} patch content cannot be empty.")
        
        validate_no_placeholder_patch_content(path, content)


def validate_patch_proposal_quality(
    *,
    deliverable: dict,
    devworker_packet: dict,
):
    return ProposalQualityService().validate(
        proposal=deliverable,
        objective=devworker_packet.get("objective", ""),
        success_criteria=devworker_packet.get("success_criteria", []),
        target_files=devworker_packet.get("target_files", []),
    )

def collect_mapped_test_identifiers(trace_result) -> list[str]:
    identifiers: list[str] = []
    for trace in trace_result.traces:
        for evidence in trace.test_evidence:
            path = evidence.file_path
            if path and path not in identifiers:
                identifiers.append(path)
    return identifiers


def build_confidence_summary(
    *,
    quality_result,
    trace_result,
    behavior_result,
    validation_result,
    runtime_result,
) -> dict:
    return ConfidenceScoringService(Path(".")).summarize(
        proposal_quality=quality_result,
        requirement_trace=trace_result,
        behavior_verification=behavior_result,
        validation_evidence=validation_result,
        runtime_execution=runtime_result,
    )



def build_promotion_readiness(
    *,
    quality_result,
    trace_result,
    behavior_result,
    validation_result,
    runtime_result,
    confidence_summary: dict,
):
    return PromotionReadinessService(Path(".")).evaluate(
        proposal_quality=quality_result,
        requirement_trace=trace_result,
        behavior_verification=behavior_result,
        validation_evidence=validation_result,
        runtime_validation=runtime_result,
        confidence_summary=confidence_summary,
    )


def build_promotion_retry_packet(
    *,
    devworker_packet: dict,
    promotion_readiness,
) -> dict:
    retry_packet = dict(devworker_packet)
    blockers = [blocker.model_dump() for blocker in promotion_readiness.blockers]
    retry_packet["promotion_readiness_retry"] = True
    retry_packet["promotion_readiness_feedback"] = "\n".join(
        blocker.get("remediation", "")
        for blocker in blockers
        if blocker.get("remediation")
    )
    retry_packet["promotion_readiness_feedback_structured"] = {
        "result": promotion_readiness.status,
        "recommendation": promotion_readiness.recommendation,
        "blockers": blockers,
    }
    retry_packet["constraints"] = dict(retry_packet.get("constraints", {}))
    retry_packet["constraints"]["promotion_readiness_retry"] = True
    retry_packet["constraints"]["require_requirement_trace"] = True
    return retry_packet

def validate_patch_proof_of_delivery(
    *,
    deliverable: dict,
    devworker_packet: dict,
):
    target_files = devworker_packet.get("target_files", [])
    proposal_paths = [
        change.get("path", "")
        for change in deliverable.get("changes", [])
        if isinstance(change, dict)
    ]
    require_test_evidence = (
        devworker_packet.get("constraints", {}).get("require_requirement_trace") is True
        or any(_is_test_path(path) for path in target_files)
        or any(_is_test_path(path) for path in proposal_paths)
    )

    trace_service = RequirementTraceService()
    trace_result = trace_service.validate(
        proposal=deliverable,
        success_criteria=devworker_packet.get("success_criteria", []),
        require_test_evidence=require_test_evidence,
    )
    behavior_result = BehavioralSmokeVerifier().verify(
        proposal=deliverable,
        objective=devworker_packet.get("objective", ""),
        success_criteria=devworker_packet.get("success_criteria", []),
    )
    if require_test_evidence:
        runtime_result = TestExecutionService(Path(".")).execute(
            devworker_packet.get("test_targets") or collect_mapped_test_identifiers(trace_result),
            proposal=deliverable,
        )
    else:
        runtime_result = TestExecutionResult(status="pass")

    validation_result = ValidationEvidenceService().validate(
        proposal=deliverable,
        trace_result=trace_result,
        behavior_result=behavior_result,
        runtime_result=runtime_result,
        require_runtime_evidence=require_test_evidence,
    )
    return trace_result, behavior_result, runtime_result, validation_result


def build_delivery_feedback_result(trace_result, behavior_result, runtime_result=None, validation_result=None):
    violations = []
    violations.extend(trace_result.violations)
    violations.extend(behavior_result.violations)
    if runtime_result is not None:
        violations.extend(runtime_result.violations)
    if validation_result is not None:
        violations.extend(validation_result.violations)
    return violations


def _is_test_path(path: str) -> bool:
    normalized = str(path).replace("\\", "/")
    return normalized.startswith("tests/") or normalized.split("/")[-1].startswith("test_")

def expand_devworker_packet_for_companion_tests(*, devworker_packet: dict, quality_result) -> dict:
    target_files = devworker_packet.get("target_files", [])
    expanded = list(target_files)
    service = PlannerWorkPacketService()

    for violation in getattr(quality_result, "violations", []):
        code = getattr(getattr(violation, "code", ""), "value", getattr(violation, "code", ""))
        if code != "unauthorized_file_change":
            continue
        proposed_file = getattr(violation, "file_path", None)
        if not proposed_file:
            continue
        expanded = service.expand_after_unauthorized_change(
            target_files=expanded,
            proposed_file=proposed_file,
        )

    if expanded == target_files:
        return devworker_packet

    retry_packet = dict(devworker_packet)
    retry_packet["target_files"] = expanded
    retry_packet["test_targets"] = sorted(
        set(retry_packet.get("test_targets", []))
        | {path for path in expanded if _is_test_path(path)}
    )
    retry_packet["constraints"] = dict(retry_packet.get("constraints", {}))
    retry_packet["constraints"]["planner_expanded_companion_test_files"] = True
    return retry_packet


def build_quality_retry_packet(
    *,
    devworker_packet: dict,
    quality_result,
) -> dict:
    retry_packet = dict(devworker_packet)
    violations = [
        violation.model_dump()
        for violation in quality_result.violations
    ]

    retry_packet["quality_retry"] = True
    retry_packet["quality_feedback"] = "\n".join(
        violation.message
        for violation in quality_result.violations
    )
    retry_packet["quality_feedback_structured"] = {
        "result": "fail",
        "violations": violations,
    }
    retry_packet["constraints"] = dict(retry_packet.get("constraints", {}))
    retry_packet["constraints"]["proposal_quality_retry"] = True
    retry_packet["constraints"]["max_proposal_quality_retries"] = MAX_PROPOSAL_QUALITY_RETRIES
    return retry_packet

def build_delivery_retry_packet(
    *,
    devworker_packet: dict,
    trace_result,
    behavior_result,
    runtime_result=None,
    validation_result=None,
) -> dict:
    retry_packet = dict(devworker_packet)
    violations = [
        violation.model_dump()
        for violation in build_delivery_feedback_result(trace_result, behavior_result, runtime_result, validation_result)
    ]
    retry_packet["quality_retry"] = True
    retry_packet["proof_of_delivery_retry"] = True
    retry_packet["quality_feedback"] = "\n".join(
        violation.get("message", "")
        for violation in violations
    )
    retry_packet["quality_feedback_structured"] = {
        "result": "fail",
        "violations": violations,
    }
    retry_packet["constraints"] = dict(retry_packet.get("constraints", {}))
    retry_packet["constraints"]["proof_of_delivery_retry"] = True
    retry_packet["constraints"]["require_requirement_trace"] = True
    return retry_packet


def compact_repo_evidence(item: dict[str, Any]) -> dict[str, Any]:
    lines = item.get("lines", [])

    line_numbers: list[int] = []

    if isinstance(lines, list):
        for line in lines:
            if not isinstance(line, dict):
                continue

            line_number = line.get("line")

            if isinstance(line_number, int):
                line_numbers.append(line_number)

    if line_numbers:
        line_range = f"{min(line_numbers)}-{max(line_numbers)}"
    elif isinstance(lines, str):
        line_range = lines
    else:
        line_range = "unknown"

    content = item.get("content", "")
    summary = item.get("summary")

    if not summary and isinstance(content, str):
        summary = content[:1000]

    compacted = {
        "file": item.get("path") or item.get("file"),
        "path": item.get("path") or item.get("file"),
        "lines": line_range,
        "summary": summary or "Repository file read.",
    }

    for key in [
        "exists",
        "requested_operation",
        "target_file_missing",
        "file_missing_create_allowed",
        "repository_evidence_status",
        "error",
    ]:
        if key in item:
            compacted[key] = item[key]

    return compacted

def evidence_has_full_file(evidence_packet: dict, path: str) -> bool:
    for item in evidence_packet.get("evidence", []):
        if item.get("path") == path and item.get("content_mode") == "full_file":
            return True
    return False


def validate_replace_file_evidence(patch_proposal: dict, evidence_packet: dict) -> list[str]:
    errors: list[str] = []

    for change in patch_proposal.get("changes", []):
        if change.get("operation") == "replace_file":
            path = change.get("path")
            if not path:
                errors.append("replace_file change is missing path.")
                continue

            if not evidence_has_full_file(evidence_packet, path):
                errors.append(
                    f"replace_file requires full_file evidence for {path}."
                )

    return errors


def filter_context_requested_files(
    requested_file_items: list[dict[str, Any]],
    repo_evidence: list[dict[str, Any]],
    constraints: dict[str, Any] | None = None,
) -> list[str]:
    constraints = constraints or {}
    allow_create = constraints.get("allow_create_files") is True or "create_file" in constraints.get("allowed_operations", [])
    missing_allowed = {
        item.get("path") or item.get("file")
        for item in repo_evidence
        if item.get("repository_evidence_status") == "missing_allowed_for_create"
        or item.get("file_missing_create_allowed") is True
    }

    requested_files: list[str] = []
    for item in requested_file_items:
        path = item.get("path") if isinstance(item, dict) else None
        if not path:
            continue
        if allow_create and path in missing_allowed:
            continue
        if path not in requested_files:
            requested_files.append(path)
    return requested_files


def handle_context_request(
    context_request: dict,
    original_evidence_packet: dict,
    context_expansion_count: int,
    max_context_expansions: int,
) -> dict:
    if context_expansion_count >= max_context_expansions:
        return {
            "chair_action": "context_expansion_limit_reached",
            "status": "blocked",
            "context_request": context_request,
        }

    requested_files = filter_context_requested_files(
        context_request.get("requested_files", []),
        original_evidence_packet.get("evidence", []),
        {"allow_create_files": True, "allowed_operations": ["replace_file", "create_file"]},
    )

    if not requested_files:
        return {
            "chair_action": "context_request_invalid",
            "status": "rejected",
            "errors": ["context_request contained no requested files."],
            "context_request": context_request,
        }

    expanded_evidence_packet = gather_repository_evidence_for_files(requested_files)

    merged_evidence_packet = merge_evidence_packets(
        original_evidence_packet,
        expanded_evidence_packet,
    )

    return run_devworker_with_evidence(
        evidence_packet=merged_evidence_packet,
        context_expansion_count=context_expansion_count + 1,
        max_context_expansions=max_context_expansions,
    )

def merge_evidence_packets(original: dict, expanded: dict) -> dict:
    merged = dict(original)
    by_path: dict[str, dict] = {}

    for item in original.get("evidence", []):
        path = item.get("path")
        if path:
            by_path[path] = item

    for item in expanded.get("evidence", []):
        path = item.get("path")
        if path:
            by_path[path] = item

    merged["evidence"] = list(by_path.values())
    return merged

def gather_repository_evidence_for_files(paths: list[str]) -> dict:
    repository_result = dispatch_agent(
        "repository",
        {
            "objective": "Gather expanded repository context.",
            "instructions": "Return full-file repository evidence for the requested files.",
            "target_files": paths,
            "requested_operation": "replace_file",
            "mode": "evidence_gathering",
            "context_mode": "full_file",
            "include_dependency_hints": True,
        },
    )

    return repository_result.get("content", repository_result)


def run_devworker_with_evidence(
    evidence_packet: dict,
    context_expansion_count: int = 0,
    max_context_expansions: int = 1,
) -> dict:
    devworker_packet = {
        "objective": evidence_packet.get("objective", "Retry with expanded repository context."),
        "target_files": evidence_packet.get("target_files", []),
        "success_criteria": evidence_packet.get("success_criteria", []),
        "repo_evidence": evidence_packet.get("evidence", []),
        "dependency_hints": evidence_packet.get("dependency_hints", []),
        "constraints": {
            "proposal_only": True,
            "no_file_writes": True,
            "must_use_repository_evidence": True,
            "must_cite_lines_when_available": True,
            "allowed_operations": ["replace_file", "create_file"],
            "allow_create_files": True,
        },
    }

    agent_result = dispatch_agent(
        "dev_worker",
        devworker_packet,
    )

    deliverable = agent_result.get("deliverable", {})

    if deliverable.get("result_type") == "context_request":
        return handle_context_request(
            context_request=deliverable,
            original_evidence_packet=evidence_packet,
            context_expansion_count=context_expansion_count,
            max_context_expansions=max_context_expansions,
        )
    
    if deliverable.get("result_type") == "patch_proposal":
        deliverable = normalize_patch_proposal_deliverable(deliverable)
        agent_result["deliverable"] = deliverable
        print(
            "[Chair] DevWorker deliverable:",
            json.dumps(deliverable, indent=2),
            flush=True,
        )
        validate_patch_proposal_deliverable(deliverable)

        quality_result = validate_patch_proposal_quality(
            deliverable=deliverable,
            devworker_packet=devworker_packet,
        )

        if not quality_result.passed:
            retry_packet = build_quality_retry_packet(
                devworker_packet=devworker_packet,
                quality_result=quality_result,
            )

            agent_result = dispatch_agent("dev_worker", retry_packet)
            deliverable = agent_result.get("deliverable", {})

            if deliverable.get("result_type") != "patch_proposal":
                validate_devworker_deliverable(deliverable)
            else:
                deliverable = normalize_patch_proposal_deliverable(deliverable, retry_count=1)
                agent_result["deliverable"] = deliverable
                validate_patch_proposal_deliverable(deliverable)
                quality_result = validate_patch_proposal_quality(
                    deliverable=deliverable,
                    devworker_packet=retry_packet,
                )

            if not quality_result.passed:
                return {
                    "chair_action": "patch_proposal_quality_rejected",
                    "status": "rejected",
                    "errors": [
                        violation.message
                        for violation in quality_result.violations
                    ],
                    "quality_result": quality_result.model_dump(),
                    "patch_proposal": deliverable,
                }

        trace_result, behavior_result, runtime_result, validation_result = validate_patch_proof_of_delivery(
            deliverable=deliverable,
            devworker_packet=devworker_packet,
        )

        if not trace_result.passed or not behavior_result.passed or not runtime_result.passed or not validation_result.passed:
            retry_packet = build_delivery_retry_packet(
                devworker_packet=devworker_packet,
                trace_result=trace_result,
                behavior_result=behavior_result,
                runtime_result=runtime_result,
                validation_result=validation_result,
            )

            agent_result = dispatch_agent("dev_worker", retry_packet)
            deliverable = agent_result.get("deliverable", {})

            if deliverable.get("result_type") != "patch_proposal":
                validate_devworker_deliverable(deliverable)
            else:
                deliverable = normalize_patch_proposal_deliverable(deliverable, retry_count=1)
                agent_result["deliverable"] = deliverable
                validate_patch_proposal_deliverable(deliverable)
                quality_result = validate_patch_proposal_quality(
                    deliverable=deliverable,
                    devworker_packet=retry_packet,
                )
                trace_result, behavior_result, runtime_result, validation_result = validate_patch_proof_of_delivery(
                    deliverable=deliverable,
                    devworker_packet=retry_packet,
                )

            if (
                not quality_result.passed
                or not trace_result.passed
                or not behavior_result.passed
                or not runtime_result.passed
                or not validation_result.passed
            ):
                delivery_violations = build_delivery_feedback_result(
                    trace_result,
                    behavior_result,
                    runtime_result,
                    validation_result,
                )
                return {
                    "chair_action": "patch_proposal_quality_rejected",
                    "status": "rejected",
                    "errors": [
                        violation.message
                        for violation in [*quality_result.violations, *delivery_violations]
                    ],
                    "quality_result": quality_result.model_dump(),
                    "requirement_trace_result": trace_result.model_dump(),
                    "behavior_verification_result": behavior_result.model_dump(),
                    "runtime_validation_result": runtime_result.model_dump(),
                    "validation_evidence_result": validation_result.model_dump(),
                    "patch_proposal": deliverable,
                }


        errors = validate_replace_file_evidence(
            deliverable,
            {
                "evidence": evidence_packet.get("evidence", []),
            },
        )

        if errors:
            return {
                "chair_action": "patch_proposal_rejected",
                "status": "rejected",
                "errors": errors,
                "patch_proposal": deliverable,
            }

        staging_service = StagingService(Path("."))

        stage_manifest = staging_service.create_stage_from_patch_proposal(
            deliverable,
            proposal_quality=quality_result.model_dump(),
            requirement_trace=RequirementTraceService().summarize(trace_result),
            behavior_verification=behavior_result.model_dump(),
            validation_summary=ValidationEvidenceService().summarize(validation_result),
            validation_evidence=validation_result.model_dump(),
            runtime_validation_summary=TestExecutionService(Path(".")).summarize(runtime_result),
            runtime_execution_evidence=runtime_result.model_dump(),
            confidence_summary=build_confidence_summary(
                quality_result=quality_result,
                trace_result=trace_result,
                behavior_result=behavior_result,
                validation_result=validation_result,
                runtime_result=runtime_result,
            ),
        )

        agent_result["stage_manifest"] = stage_manifest.to_dict()
        agent_result["patch_id"] = stage_manifest.patch_id

    return agent_result

def validate_no_placeholder_patch_content(path: str, content: str) -> None:
    lowered = content.lower()

    forbidden_markers = [
        "<new file content",
        "<placeholder",
        "todo",
        "pass\n",
        "pass\r\n",
        "based on requirements",
    ]

    for marker in forbidden_markers:
        if marker in lowered:
            raise ValueError(f"{path} contains placeholder/stub content.")

    if path.startswith("tests/") and not has_test_assertion(content):
        raise ValueError(f"{path} test file contains no assertions. diagnostics={build_assertion_diagnostics(content)}")


def has_test_assertion(content: str) -> bool:
    try:
        import ast
        tree = ast.parse(content)
    except SyntaxError:
        return "assert " in content or "pytest.raises" in content or ".assert" in content

    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            if isinstance(node.test, ast.Constant) and node.test.value is True:
                continue
            return True

        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr == "raises" and isinstance(func.value, ast.Name) and func.value.id == "pytest":
                    return True
                if func.attr.startswith("assert"):
                    if func.attr == "assertTrue" and node.args:
                        first_arg = node.args[0]
                        if isinstance(first_arg, ast.Constant) and first_arg.value is True:
                            continue
                    return True

    return False


def build_assertion_diagnostics(content: str) -> dict[str, int]:
    try:
        import ast
        tree = ast.parse(content)
    except SyntaxError:
        return {
            "assert_keyword_count": content.count("assert "),
            "unittest_assert_count": content.count(".assert"),
            "pytest_raises_count": content.count("pytest.raises"),
            "syntax_error": 1,
        }

    diagnostics = {
        "assert_keyword_count": 0,
        "unittest_assert_count": 0,
        "pytest_raises_count": 0,
        "meaningful_assertion_count": 0,
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            diagnostics["assert_keyword_count"] += 1
            if not (isinstance(node.test, ast.Constant) and node.test.value is True):
                diagnostics["meaningful_assertion_count"] += 1

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            func = node.func
            if func.attr == "raises" and isinstance(func.value, ast.Name) and func.value.id == "pytest":
                diagnostics["pytest_raises_count"] += 1
                diagnostics["meaningful_assertion_count"] += 1
            elif func.attr.startswith("assert"):
                diagnostics["unittest_assert_count"] += 1
                if not (func.attr == "assertTrue" and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value is True):
                    diagnostics["meaningful_assertion_count"] += 1

    return diagnostics


def extract_target_file_hints(objective: str) -> list[str]:
    if not isinstance(objective, str):
        return []
    hints: list[str] = []
    for token in objective.replace("\n", " ").split():
        cleaned = token.strip("`'\".,;:()[]{}")
        if "/" not in cleaned:
            continue
        if not cleaned.endswith((".py", ".json", ".toml", ".md", ".txt", ".yaml", ".yml")):
            continue
        if cleaned.startswith("/") or ".." in cleaned.split("/"):
            continue
        if cleaned not in hints:
            hints.append(cleaned)
    return hints

def parse_chair_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Ageix Chair orchestrator.")
    parser.add_argument("--objective", help="Objective text to execute.")
    parser.add_argument("--objective-file", help="Path to a file containing the objective.")
    parser.add_argument("--project-id", default="ageix", help="Project identifier.")
    parser.add_argument("--answer-file", help="JSON file containing structured discovery answers.")
    parser.add_argument("--allow-assumptions", action="store_true", help="Allow planning to proceed with explicit assumptions when only user clarification is missing.")
    return parser.parse_args()

#-----------------------------------------------------------------------#

if __name__ == "__main__":
    import json

    args = parse_chair_args()

    objective_envelope = ObjectiveSourceService(Path(".")).resolve_objective(
        objective_text=args.objective,
        objective_file=args.objective_file,
        project_id=args.project_id,
    )

    sprint_prompt = objective_envelope["description"]

    task = {
        "title": "Ageix Sprint 10.0",
        "description": sprint_prompt,
    }

    target_files = []
    if args.objective_file:
        target_files = [args.objective_file]
    elif args.objective:
        target_files = extract_target_file_hints(args.objective)

    if target_files:
        task["target_files"] = target_files
        task["metadata"] = {
            "objective_file_as_target_hint": bool(args.objective_file),
            "target_files": target_files,
        }

    discovery_service = DiscoveryService()
    discovery_answers = discovery_service.load_answers(args.answer_file)
    discovery_result = discovery_service.analyze(
        objective=sprint_prompt,
        target_files=target_files,
        answers=discovery_answers,
        allow_assumptions=args.allow_assumptions,
    )

    if not discovery_result.ready:
        resolution_result = DiscoveryResolutionService(Path(".")).resolve(
            objective=sprint_prompt,
            target_files=target_files,
            answers=discovery_answers,
            run_id=objective_envelope.get("run_id") or args.project_id,
            execute_research=True,
            execute_architecture_review=True,
            persist=True,
        )
        if not resolution_result.ready:
            print(json.dumps({
                "chair_action": "discovery_required",
                "status": resolution_result.status,
                "task": task,
                "discovery": resolution_result.discovery.model_dump(),
                "discovery_resolution": resolution_result.model_dump(),
                "executed_count": 0,
            }, indent=2))
            raise SystemExit(0)
        discovery_result = resolution_result.discovery

    resolution_payload = resolution_result.model_dump() if "resolution_result" in locals() else {}
    plan_result = build_plan_for_task(task=task, discovery_resolution=resolution_payload)
    state = create_chair_state(task, plan_result)
    state["discovery"] = discovery_result.model_dump()

    state = execute_ready_steps_until_blocked_or_done(state)

    print(json.dumps(state, indent=2))