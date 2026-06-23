import json
from typing import Any
from services.llm_service import invoke_llm
from schemas.plan_schema import ExecutionPlan
from services.planner_work_packet_service import PlannerWorkPacketService

from utils.prompt_loader import load_prompt

SYSTEM_PROMPT = load_prompt(
    "planner_system.txt"
)

def build_planner_prompt(
    task: dict,
    parent_task: dict | None = None,
    sibling_tasks: list[dict] | None = None,
    conversation_summary: str = "",
    recent_messages: list[dict] | None = None,
    task_events: list[dict] | None = None,
    known_files: list[str] | None = None,
) -> str:
    return f"""
{SYSTEM_PROMPT}

Runtime Context:

Conversation Summary:
{conversation_summary}

Current Task:
{json.dumps(task, indent=2)}

Parent Task:
{json.dumps(parent_task or {}, indent=2)}

Sibling Tasks:
{json.dumps(sibling_tasks or [], indent=2)}

Recent Messages:
{json.dumps(recent_messages or [], indent=2)}

Task Events:
{json.dumps(task_events or [], indent=2)}

Known Project Files:
{json.dumps(known_files or [], indent=2)}
""".strip()

def extract_json(raw: str) -> dict:
    cleaned = raw.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()

    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()

    return json.loads(cleaned)


def execute_planner_agent(
    task: dict,
    parent_task: dict | None = None,
    sibling_tasks: list[dict] | None = None,
    conversation_summary: str = "",
    recent_messages: list[dict] | None = None,
    task_events: list[dict] | None = None,
    known_files: list[str] | None = None,
    discovery_resolution: dict[str, Any] | None = None,
) -> dict:
    prompt = build_planner_prompt(
        task=task,
        parent_task=parent_task,
        sibling_tasks=sibling_tasks,
        conversation_summary=conversation_summary,
        recent_messages=recent_messages,
        task_events=task_events,
        known_files=known_files,
    )

    result = invoke_llm(
        purpose="planning",
        prompt=prompt,
    )
    
    raw = result.get("response", "")

    warnings = []

    try:
        data = extract_json(raw)

        if isinstance(data, list):
            data = {
                "objective": task.get("title", "Generated execution plan"),
                "strategy": "Execute steps in dependency order.",
                "steps": data,
                "metadata": {
                    "normalized_from": "raw_step_list"
                },
            }

        if "work_plan" in data and "steps" not in data:
            data = {
                "objective": task.get("title", "Generated execution plan"),
                "strategy": "Execute the generated work plan in dependency order.",
                "steps": data["work_plan"],
                "metadata": {
                    "normalized_from": "work_plan"
                },
            }

        if "plan" in data and "steps" not in data:
            plan_steps = []

            for idx, (step_id, step_data) in enumerate(data["plan"].items(), start=1):
                plan_steps.append({
                    "id": step_id,
                    "agent": "repository" if idx == 1 else "dev_worker",
                    "objective": step_data.get("action", step_id),
                    "instructions": step_data.get("description", ""),
                    "target_files": step_data.get("target_files", []),
                    "inputs": {},
                    "expected_output": {},
                    "constraints": {},
                    "success_criteria": [],
                    "dependencies": [],
                })

            data = {
                "objective": task.get("title", "Generated execution plan"),
                "strategy": "Normalized from legacy plan format.",
                "steps": plan_steps,
                "metadata": {
                    "normalized_from": "legacy_plan_object"
                },
            }

        if "objective" not in data:
            data["objective"] = task.get("title", "Generated execution plan")

        if "strategy" not in data:
            data["strategy"] = "Execute steps in dependency order."
        
        
        for step in data.get("steps", []):

            if step.get("agent") == "dev_worker":
                target_files = step.get("target_files") or step.get("inputs", {}).get("target_files")

                if not target_files:
                    warnings.append(
                        {
                            "step_id": step.get("id"),
                            "level": "warning",
                            "code": "DEV_WORKER_TARGET_FILES_MISSING",
                            "message": "DevWorker step missing target_files; repository discovery required.",
                        }
                    )

            if isinstance(step.get("expected_output"), str):
                step["expected_output"] = {"description": step["expected_output"]}

            if isinstance(step.get("constraints"), str):
                step["constraints"] = {"description": step["constraints"]}

            if isinstance(step.get("success_criteria"), str):
                step["success_criteria"] = [step["success_criteria"]]

        
        plan = ExecutionPlan(**data)
        validation_error = None

        work_packet = PlannerWorkPacketService().build(
            objective=" ".join([str(task.get("title", "")), str(task.get("description", ""))]).strip() or plan.objective,
            task=task,
            planner_data=data,
            discovery_resolution=discovery_resolution,
            known_files=known_files,
        )
        data["work_packet"] = work_packet.model_dump()

    except Exception as ex:
        validation_error = str(ex)
        plan = ExecutionPlan(
            objective="Planner Validation Failure",
            strategy="Fallback plan created because planner output could not be validated.",
            steps=[],
            metadata={
                "error": validation_error,
                "raw_response": raw,
            },
        )
        data = plan.model_dump()
        work_packet = PlannerWorkPacketService().build(
            objective=" ".join([str(task.get("title", "")), str(task.get("description", ""))]).strip() or plan.objective,
            task=task,
            discovery_resolution=discovery_resolution,
            known_files=known_files,
        )
        data["work_packet"] = work_packet.model_dump()

    print(
        f"[Planner] objective='{plan.objective}' "
        f"steps={len(plan.steps)}"
    )

    return {
        "agent_name": "planner",
        "turn_type": "plan",
        "content": data,
        "raw_response": raw,
        "validation_error": validation_error,
        "warnings": warnings,
        "route": result.get("route"),
        "model_key": result.get("model_key"),
        "model": result.get("model"),
        "reason": result.get("reason"),
        "elapsed_ms": result.get("elapsed_ms"),
    }

def run(payload: dict[str, Any]) -> dict[str, Any]:
    task = payload.get("task")

    if task is None:
        raise ValueError("Planner agent requires 'task'")
    

    return execute_planner_agent(
        task=task,
        parent_task=payload.get("parent_task"),
        sibling_tasks=payload.get("sibling_tasks"),
        conversation_summary=payload.get("conversation_summary", ""),
        recent_messages=payload.get("recent_messages"),
        task_events=payload.get("task_events"),
        known_files=payload.get("known_files"),
        discovery_resolution=payload.get("discovery_resolution"),
    )



if __name__ == "__main__":
    import json

    result = execute_planner_agent(
        task={
            "title": "Compare Oracle CPQ and Salesforce CPQ",
            "description": "Create a comparison and recommendation."
        }
    )

    print(json.dumps(result, indent=2))