from __future__ import annotations

from collaboration_turn import CollaborationTurn, CollaborationDecision


EXECUTION_TERMS = [
    "build",
    "create",
    "patch",
    "modify",
    "update",
    "refactor",
    "implement",
    "test",
    "run",
    "fix",
]

REPOSITORY_TERMS = [
    "repository agent",
    "repo agent",
    "inspect",
    "read",
    "search",
    "directory structure",
    "file list",
    "list files",
    "show files",
]


def route_collaboration_turn(turn: CollaborationTurn) -> CollaborationDecision:
    text = turn.content.lower()

    addressed_to_ageix = (
        turn.target == "ageix"
        or "ageix" in text
        or "dev worker" in text
        or "devworker" in text
    )

    looks_executable = any(term in text for term in EXECUTION_TERMS)

    if turn.intent != "instruction":
        return CollaborationDecision(
            should_execute=False,
            reason=f"Turn intent '{turn.intent}' is not executable.",
        )

    wants_repository = any(term in text for term in REPOSITORY_TERMS)

    if addressed_to_ageix and wants_repository:
        return CollaborationDecision(
            should_execute=True,
            target_agent="repository",
            objective=turn.content[:120],
            instructions=[turn.content],
            reason="Read-only repository inspection requested.",
        )

    if turn.intent == "instruction" and addressed_to_ageix:
        return CollaborationDecision(
            should_execute=True,
            target_agent="dev_worker",
            objective=turn.content[:120],
            instructions=[turn.content],
            reason="Explicit instruction targeted to Ageix.",
        )

    if addressed_to_ageix and looks_executable:
        return CollaborationDecision(
            should_execute=True,
            target_agent="dev_worker",
            objective=turn.content[:120],
            instructions=[turn.content],
            reason="Executable collaboration turn addressed to Ageix.",
        )

    return CollaborationDecision(
        should_execute=False,
        reason="Turn treated as shared discussion.",
    )