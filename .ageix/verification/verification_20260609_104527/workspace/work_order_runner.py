from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from artifact_store import create_artifact, load_artifact
from evaluator_agent import evaluate_deliverable
from work_order import WorkOrder


AgentFn = Callable[[dict[str, Any]], dict[str, Any]]


def run_work_order(
    work_order: WorkOrder,
    agent_registry: dict[str, AgentFn],
) -> dict[str, Any]:
    if work_order.agent not in agent_registry:
        raise ValueError(f"No registered agent for: {work_order.agent}")

    loaded_artifacts = [
        asdict(load_artifact(artifact_id))
        for artifact_id in work_order.input_artifacts
    ]

    packet = {
        "work_order": asdict(work_order),
        "artifacts": loaded_artifacts,
    }

    agent_result = agent_registry[work_order.agent](packet)

    deliverable = agent_result.get("deliverable", agent_result)

    artifact = create_artifact(
        artifact_type=work_order.deliverable.get("type", "agent_deliverable"),
        created_by=work_order.agent,
        content={
            "work_order": asdict(work_order),
            "deliverable": deliverable,
            "raw_agent_result": agent_result,
        },
    )

    evaluation = evaluate_deliverable(
        work_order=asdict(work_order),
        deliverable=deliverable,
    )

    return {
        "work_order_id": work_order.work_order_id,
        "agent": work_order.agent,
        "artifact_id": artifact.artifact_id,
        "deliverable": deliverable,
        "evaluation": evaluation,
    }