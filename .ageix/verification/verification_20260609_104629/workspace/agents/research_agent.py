from typing import Any

from services.llm_service import invoke_llm


def build_research_prompt(
    objective: str,
    instructions: str,
    constraints: dict,
    artifacts: list,
) -> str:

    return f"""
    You are the Ageix Research Agent.

    Objective:
    {objective}

    Instructions:
    {instructions}

    Constraints:
    {constraints}

    Input Artifacts:
    {artifacts}

    Your job is to execute the work order.

    Provide:

    1. Executive Summary
    2. Key Findings
    3. Supporting Evidence

    Respond ONLY with information relevant to the objective.
    """.strip()


def run(payload: dict[str, Any]) -> dict[str, Any]:

    work_order = payload.get("work_order", {})
    artifacts = payload.get("artifacts", [])

    objective = work_order.get("objective", "")
    instructions = "\n".join(
        work_order.get("instructions", [])
    )

    constraints = work_order.get("constraints", {})

    prompt = build_research_prompt(
        objective=objective,
        instructions=instructions,
        constraints=constraints,
        artifacts=artifacts,
    )

    result = invoke_llm(
        purpose="research",
        prompt=prompt,
        context=payload,
    )

    if result.get("status") == "failed":
        return {
            "agent": "research",
            "status": "failed",
            "summary": "",
            "findings": [],
            "sources": [],
            "error": result.get("error"),
            "route": result.get("route"),
            "model": result.get("model"),
        }

    return {
        "agent": "research",
        "status": "completed",
        "summary": result.get("response", ""),
        "findings": [],
        "sources": [],
        "route": result.get("route"),
        "model_key": result.get("model_key"),
        "model": result.get("model"),
        "reason": result.get("reason"),
        "fallback_used": result.get("fallback_used", False),
    }