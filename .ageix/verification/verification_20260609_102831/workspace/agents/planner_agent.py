import json
from typing import Any
from services.llm_service import invoke_llm
from schemas.plan_schema import ExecutionPlan

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

    try:
        data = extract_json(raw)

        if "work_plan" in data and "steps" not in data:
            data = {
                "objective": task.get("title", "Generated execution plan"),
                "strategy": "Execute the generated work plan in dependency order.",
                "steps": data["work_plan"],
                "metadata": {
                    "normalized_from": "work_plan"
                },
            }

        def normalize_plan(data: dict, task: dict) -> dict:
            if "work_plan" in data and "steps" not in data:
                data["steps"] = data.pop("work_plan")

            if "objective" not in data:
                data["objective"] = task.get("title", "Generated execution plan")

            if "strategy" not in data:
                data["strategy"] = "Execute steps in dependency order."

            for step in data.get("steps", []):
                if isinstance(step.get("expected_output"), str):
                    step["expected_output"] = {
                        "description": step["expected_output"]
                    }

                if isinstance(step.get("constraints"), str):
                    step["constraints"] = {
                        "description": step["constraints"]
                    }

                if isinstance(step.get("success_criteria"), str):
                    step["success_criteria"] = [
                        step["success_criteria"]
                    ]

            return data

        data = extract_json(raw)
        data = normalize_plan(data, task)

        plan = ExecutionPlan(**data)
        validation_error = None

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

    print(
        f"[Planner] objective='{plan.objective}' "
        f"steps={len(plan.steps)}"
    )

    return {
        "agent_name": "planner",
        "turn_type": "plan",
        "content": plan.model_dump(),
        "raw_response": raw,
        "validation_error": validation_error,
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