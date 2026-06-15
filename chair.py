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

    try:
        if agent_key == "dev_worker":
            agent_result: dict[str, Any] = {}
            devworker_packet: dict[str, Any] = {}

            for expansion_attempt in range(max_context_expansions + 1):
                repository_result = dispatch_agent(
                    "repository",
                    {
                        "objective": step.get("objective", ""),
                        "instructions": step.get("instructions", ""),
                        "target_files": step.get("target_files", []),
                        "mode": "evidence_gathering",
                        "include_dependency_hints": True,
                    },
                )

                repository_content = repository_result.get("content", repository_result)

                devworker_packet = build_devworker_packet(
                    objective=step.get("objective", ""),
                    target_files=step.get("target_files", []),
                    repository_result=repository_content,
                    step_constraints=step.get("constraints", {}),
                    success_criteria=step.get("success_criteria", []),
                )

                devworker_packet["instructions"] = step.get("instructions", "")
                devworker_packet["expected_output"] = step.get("expected_output", {})
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

                requested_files = [
                    item.get("path")
                    for item in deliverable.get("requested_files", [])
                    if item.get("path")
                ]

                step["target_files"] = sorted(
                    set(step.get("target_files", [])) | set(requested_files)
                )

            deliverable = agent_result.get("deliverable", {})

            if deliverable.get("result_type") == "patch_proposal":
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

                trace_result, behavior_result = validate_patch_proof_of_delivery(
                    deliverable=deliverable,
                    devworker_packet=devworker_packet,
                )

                if not trace_result.passed or not behavior_result.passed:
                    retry_packet = build_delivery_retry_packet(
                        devworker_packet=devworker_packet,
                        trace_result=trace_result,
                        behavior_result=behavior_result,
                    )

                    agent_result = dispatch_agent("dev_worker", retry_packet)
                    deliverable = agent_result.get("deliverable", {})

                    if deliverable.get("result_type") != "patch_proposal":
                        validate_devworker_deliverable(deliverable)
                    else:
                        validate_patch_proposal_deliverable(deliverable)
                        quality_result = validate_patch_proposal_quality(
                            deliverable=deliverable,
                            devworker_packet=retry_packet,
                        )
                        trace_result, behavior_result = validate_patch_proof_of_delivery(
                            deliverable=deliverable,
                            devworker_packet=retry_packet,
                        )

                    if (
                        not quality_result.passed
                        or not trace_result.passed
                        or not behavior_result.passed
                    ):
                        delivery_violations = build_delivery_feedback_result(
                            trace_result,
                            behavior_result,
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

                manifest = PatchBuilder(Path(".")).stage_patch_from_deliverable(
                    deliverable,
                    proposal_quality=quality_result.model_dump(),
                    requirement_trace=RequirementTraceService().summarize(trace_result),
                    behavior_verification=behavior_result.model_dump(),
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
        "repo_evidence": repo_evidence,
        "dependency_hints": repository_result.get("dependency_hints", []),
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
    
def validate_patch_proposal_deliverable(
    deliverable: dict[str, Any]
) -> None:

    required = [
        "result_type",
        "objective",
        "summary",
        "files_considered",
        "evidence_used",
        "dependency_hints_used",
        "assumptions",
        "dependency_risks",
        "changes",
        "test_plan",
        "no_write_confirmation",
    ]

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
        raise ValueError(
            f"Patch proposal missing fields: {missing}"
        )

    seen_paths: set[str] = set()

    for change in deliverable["changes"]:
        path = change.get("path")
        operation = change.get("operation")
        content = change.get("content")

        for marker in forbidden:
            if marker.lower() in content.lower():
                raise ValueError(
                    f"{path} contains placeholder content."
                )

        if operation not in {"replace_file", "create_file"}:
            raise ValueError(
                f"Unsupported patch proposal operation: {operation}"
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
    return trace_result, behavior_result


def build_delivery_feedback_result(trace_result, behavior_result):
    violations = []
    violations.extend(trace_result.violations)
    violations.extend(behavior_result.violations)
    return violations


def _is_test_path(path: str) -> bool:
    normalized = str(path).replace("\\", "/")
    return normalized.startswith("tests/") or normalized.split("/")[-1].startswith("test_")

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
) -> dict:
    retry_packet = dict(devworker_packet)
    violations = [
        violation.model_dump()
        for violation in build_delivery_feedback_result(trace_result, behavior_result)
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

    return {
        "file": item.get("path") or item.get("file"),
        "lines": line_range,
        "summary": summary or "Repository file read.",
    }

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

    requested_files = [
        item["path"]
        for item in context_request.get("requested_files", [])
        if item.get("path")
    ]

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

        trace_result, behavior_result = validate_patch_proof_of_delivery(
            deliverable=deliverable,
            devworker_packet=devworker_packet,
        )

        if not trace_result.passed or not behavior_result.passed:
            retry_packet = build_delivery_retry_packet(
                devworker_packet=devworker_packet,
                trace_result=trace_result,
                behavior_result=behavior_result,
            )

            agent_result = dispatch_agent("dev_worker", retry_packet)
            deliverable = agent_result.get("deliverable", {})

            if deliverable.get("result_type") != "patch_proposal":
                validate_devworker_deliverable(deliverable)
            else:
                validate_patch_proposal_deliverable(deliverable)
                quality_result = validate_patch_proposal_quality(
                    deliverable=deliverable,
                    devworker_packet=retry_packet,
                )
                trace_result, behavior_result = validate_patch_proof_of_delivery(
                    deliverable=deliverable,
                    devworker_packet=retry_packet,
                )

            if (
                not quality_result.passed
                or not trace_result.passed
                or not behavior_result.passed
            ):
                delivery_violations = build_delivery_feedback_result(
                    trace_result,
                    behavior_result,
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

    if path.startswith("tests/") and "assert " not in content:
        raise ValueError(f"{path} test file contains no assertions.")


def parse_chair_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Ageix Chair orchestrator.")
    parser.add_argument("--objective", help="Objective text to execute.")
    parser.add_argument("--objective-file", help="Path to a file containing the objective.")
    parser.add_argument("--project-id", default="ageix", help="Project identifier.")
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

    plan_result = build_plan_for_task(task=task)
    state = create_chair_state(task, plan_result)

    state = execute_ready_steps_until_blocked_or_done(state)

    print(json.dumps(state, indent=2))