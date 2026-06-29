# agents/registry.py

from typing import Any


AGENT_REGISTRY: dict[str, dict[str, Any]] = {
    "planner": {
        "name": "Planner Agent",
        "description": "Creates structured execution plans from user objectives.",
        "handler": "agents.planner_agent.run",
        "default_model_profile": "reasoning_balanced",
        "allowed_model_profiles": [
            "local_fast",
            "reasoning_balanced",
            "cloud_deep_reasoning",
        ],
        "capabilities": [
            "planning",
            "task_decomposition",
            "dependency_mapping",
        ],
    },
    "research": {
        "name": "Research Agent",
        "description": "Finds, summarizes, and cites information.",
        "handler": "agents.research_agent.run",
        "default_model_profile": "cloud_research",
        "allowed_model_profiles": [
            "local_fast",
            "cloud_research",
            "cloud_deep_reasoning",
        ],
        "capabilities": [
            "research",
            "summarization",
            "source_collection",
        ],
    },
    "dev_worker": {
        "name": "Development Worker Agent",
        "description": "Executes development tasks against a codebase.",
        "handler": "agents.dev_worker_agent.run",
        "default_model_profile": "reasoning_balanced",
        "allowed_model_profiles": [
            "local_fast",
            "reasoning_balanced",
            "cloud_deep_reasoning",
        ],
        "capabilities": [
            "code_review",
            "code_modification",
            "testing",
            "debugging",
        ],
    },
    "repository": {
        "name": "Repository Agent",
        "description": "Inspects repository structure and gathers read-only code evidence.",
        "handler": "agents.repository_agent.run",
        "default_model_profile": "local_fast",
        "allowed_model_profiles": [
            "local_fast",
            "reasoning_balanced",
        ],
        "capabilities": [
            "repo_file_listing",
            "repo_file_read",
            "code_search",
            "directory_inspection",
        ],
    },
    "conversation_evaluator": {
        "name": "Conversation Evaluator Agent",
        "description": "Evaluates shared conversation turns for summary and deadlock confidence.",
        "handler": "agents.conversation_evaluator_agent.run",
        "default_model_profile": "reasoning_balanced",
        "allowed_model_profiles": [
            "local_fast",
            "reasoning_balanced",
        ],
        "capabilities": [
            "conversation_summarization",
            "deadlock_assessment",
        ],
    },
}


def get_agent(agent_key: str) -> dict[str, Any]:
    agent = AGENT_REGISTRY.get(agent_key)

    if agent is None:
        raise ValueError(f"Unknown agent: {agent_key}")

    return agent


def list_agents() -> dict[str, dict[str, Any]]:
    return AGENT_REGISTRY


def agent_exists(agent_key: str) -> bool:
    return agent_key in AGENT_REGISTRY