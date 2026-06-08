from typing import Any
import copy
from agents.dispatcher import dispatch_agent
from work_order_runner import run_work_order


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
    return {
        "task": task,
        "status": "planned",
        "plan": plan_result.get("plan", {}),
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


def execute_ready_step(state: dict[str, Any]) -> dict[str, Any]:
    ready_steps = get_ready_steps(state)

    if not ready_steps:
        state["chair_action"] = "no_ready_steps"
        return update_plan_status(state)

    step = ready_steps[0]
    agent_key = normalize_agent_key(step.get("agent", "research"))

    step["status"] = "in_progress"

    try:
        if agent_key == "dev_worker":
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

            repository_content = repository_result.get(
                "content",
                repository_result,
            )

            devworker_packet = build_devworker_packet(
                objective=step.get("objective", ""),
                target_files=step.get("target_files", []),
                repository_result=repository_content,
            )

            print("[Chair] DevWorker packet repo evidence count:", len(devworker_packet.get("repo_evidence", [])), flush=True)

            devworker_packet["instructions"] = step.get("instructions", "")
            devworker_packet["expected_output"] = step.get("expected_output", {})

            agent_result = dispatch_agent(
                "dev_worker",
                devworker_packet,
            )

            validate_devworker_deliverable(
                agent_result.get("deliverable", {})
            )

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
) -> dict:
    repo_evidence = repository_result.get("evidence", [])

    if not repo_evidence:
        repo_evidence = [
            compact_repo_evidence(item)
            for item in repository_result.get("read_files", [])
        ]

    return {
        "objective": objective,
        "target_files": target_files,
        "repo_evidence": repo_evidence,
        "dependency_hints": repository_result.get("dependency_hints", []),
        "constraints": {
            "proposal_only": True,
            "no_file_writes": True,
            "must_use_repository_evidence": True,
            "must_cite_lines_when_available": True,
        },
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

#-----------------------------------------------------------------------#

if __name__ == "__main__":
    import json

    task = {
        "title": "Test Dev Worker",
        "description": "Verify dev worker routing."
    }

    plan_result = build_plan_for_task(task=task)
    state = create_chair_state(task, plan_result)

    state["plan"] = {
    "steps": [
        {
            "id": "step_1",
            "agent": "dev_worker",
            "objective": "Review DevWorker evidence-aware proposal flow.",
            "instructions": "Use repository evidence from agents/dev_worker_agent.py and chair.py to propose next implementation steps. Do not modify files.",
            "target_files": [
                "agents/dev_worker_agent.py",
                "chair.py",
            ],
            "expected_output": {
                "type": "proposal"
            },
            "constraints": {
                "proposal_only": True
            },
            "status": "pending",
            "dependencies": []
        }
    ]
}

    state = execute_ready_steps_until_blocked_or_done(state)
    
    print(json.dumps(state, indent=2))