from __future__ import annotations

from models.agent_role import AgentRole

CONFIDENCE_THRESHOLDS: dict[str, float] = {
    "architect": 4.0,
    "worker": 6.0,
    "governance": 7.0,
}

ROLE_THRESHOLD_GROUP: dict[AgentRole, str] = {
    AgentRole.CLAUDE_AI: "architect",
    AgentRole.LEX: "architect",
    AgentRole.CLAUDE_CODE: "worker",
    AgentRole.AGEIX_INTERNAL: "worker",
    AgentRole.AGEIX_CHAIR: "governance",
}

TURN_LIMIT_PER_THREAD = 6

DIRECTED_QUESTION_RESPONSE_TYPES: tuple[str, ...] = ("ANSWER", "QUESTION", "ABSTAIN", "ESCALATE")


def confidence_threshold_for_role(role: AgentRole) -> float:
    group = ROLE_THRESHOLD_GROUP.get(role, "worker")
    return CONFIDENCE_THRESHOLDS[group]
