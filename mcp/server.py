"""Ageix MCP server.

Exposes Ageix task/conversation/collaboration APIs as MCP tools.
Wraps the Ageix HTTP API via httpx — no direct imports from app.py.

Usage:
    python mcp/server.py                   # stdio (Claude Code)
    python mcp/server.py --transport sse   # SSE on port 8001 (claude.ai)

Environment:
    AGEIX_BASE_URL  Base URL of the running Ageix instance (default: http://localhost:8000)
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

# The local mcp/ directory has the same name as the installed mcp package.
# If the project root is in sys.path (PYTHONPATH, -m, etc.), it will shadow
# the installed package. Remove it before importing FastMCP.
_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_this_dir)
sys.path = [p for p in sys.path if os.path.abspath(p) != _project_root]

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

AGEIX_BASE_URL = os.environ.get("AGEIX_BASE_URL", "http://localhost:8000").rstrip("/")

# By default FastMCP only allows localhost. When running behind a reverse proxy
# (nginx → ageix.wilsongpt.com), the Host header is the public domain. Allow it
# via AGEIX_ALLOWED_HOST; multiple values can be comma-separated.
_extra_hosts = [
    h.strip()
    for h in os.environ.get("AGEIX_ALLOWED_HOST", "").split(",")
    if h.strip()
]
_transport_security = TransportSecuritySettings(
    allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"] + _extra_hosts
)

mcp = FastMCP("Ageix", port=8001, transport_security=_transport_security)


# ---------------------------------------------------------------------------
# Shared HTTP helper
# ---------------------------------------------------------------------------

async def _get(path: str, **params: Any) -> dict[str, Any]:
    filtered = {k: v for k, v in params.items() if v is not None}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{AGEIX_BASE_URL}{path}", params=filtered)
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        return {"error": f"Cannot reach Ageix at {AGEIX_BASE_URL}. Is it running?"}
    except Exception as exc:
        return {"error": str(exc)}


async def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{AGEIX_BASE_URL}{path}", json=body)
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        return {"error": f"Cannot reach Ageix at {AGEIX_BASE_URL}. Is it running?"}
    except Exception as exc:
        return {"error": str(exc)}


async def _patch(path: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.patch(f"{AGEIX_BASE_URL}{path}", json=body)
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        return {"error": f"Cannot reach Ageix at {AGEIX_BASE_URL}. Is it running?"}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def ageix_health() -> dict[str, Any]:
    """Ping the Ageix health endpoint to verify connectivity."""
    return await _get("/health")


@mcp.tool()
async def ageix_get_project_status(conversation_id: str) -> dict[str, Any]:
    """Read the current state of all active tasks in a conversation.

    Fetches every top-level task, then pulls each task's Chair briefing so you
    get a full status snapshot without manual queries.
    """
    tasks_resp = await _get("/v1/ageix/tasks", conversation_id=conversation_id)
    if "error" in tasks_resp:
        return tasks_resp

    tasks = tasks_resp.get("tasks", [])
    results = []
    for task in tasks:
        task_id = task.get("task_id") or task.get("id")
        briefing = await _get(f"/v1/ageix/tasks/{task_id}/chair/briefing")
        results.append({"task": task, "briefing": briefing})

    return {"conversation_id": conversation_id, "task_count": len(results), "tasks": results}


@mcp.tool()
async def ageix_get_task_tree(task_id: str) -> dict[str, Any]:
    """Get the full subtask tree for a parent task, including all child statuses."""
    return await _get(f"/v1/ageix/tasks/{task_id}/tree")


@mcp.tool()
async def ageix_create_task(
    conversation_id: str,
    title: str,
    description: str,
    priority: str = "normal",
    owner: str = "user",
) -> dict[str, Any]:
    """Create a new governed task.

    Args:
        conversation_id: Shared namespace (e.g. "ageix-main").
        title: Short task title.
        description: Full task description.
        priority: "normal", "high", or "low".
        owner: "planner", "dev_worker", or "user".
    """
    return await _post("/v1/ageix/tasks", {
        "conversation_id": conversation_id,
        "title": title,
        "description": description,
        "priority": priority,
        "owner": owner,
    })


@mcp.tool()
async def ageix_plan_task(task_id: str) -> dict[str, Any]:
    """Ask the Ageix planner to decompose a task into concrete subtasks.

    Returns the parent task plus all created subtasks.
    """
    return await _post(f"/v1/ageix/tasks/{task_id}/plan", {})


@mcp.tool()
async def ageix_update_task(
    task_id: str,
    status: str | None = None,
    owner: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Update a task's status, owner, or description.

    Args:
        task_id: ID of the task to update.
        status: "todo", "in_progress", "planned", "completed", or "blocked".
        owner: New owner agent name (optional).
        description: Replacement description (optional).
    """
    body: dict[str, Any] = {}
    if status is not None:
        body["status"] = status
    if owner is not None:
        body["owner"] = owner
    if description is not None:
        body["description"] = description
    return await _patch(f"/v1/ageix/tasks/{task_id}", body)


@mcp.tool()
async def ageix_post_collaboration_turn(
    conversation_id: str,
    speaker: str,
    target: str,
    intent: str,
    content: str,
) -> dict[str, Any]:
    """Post a structured message from one agent to another.

    This is the primary communication channel between architect and dev worker.

    Args:
        conversation_id: Shared namespace.
        speaker: "greg", "chatgpt", "ageix", "chair", or "agent".
        target: Any string label for the intended recipient.
        intent: "discussion", "instruction", "change_plan", "approved_execution",
                "question", "execution_result", "review", "blocker", or "status".
        content: Message body.
    """
    return await _post("/v1/ageix/collaboration/turns", {
        "conversation_id": conversation_id,
        "speaker": speaker,
        "target": target,
        "intent": intent,
        "content": content,
    })


@mcp.tool()
async def ageix_get_collaboration_turns(
    conversation_id: str,
    limit: int = 20,
) -> dict[str, Any]:
    """Read the ordered message history between agents in a conversation.

    Returns speaker, target, intent, content, and timestamp for each turn.
    """
    return await _get(f"/v1/ageix/collaboration/{conversation_id}/turns", limit=limit)


@mcp.tool()
async def ageix_post_agent_turn(
    task_id: str,
    conversation_id: str,
    agent_name: str,
    content: str,
    turn_type: str = "analysis",
    visibility: str = "internal",
) -> dict[str, Any]:
    """Record a unit of agent work in the audit trail.

    Args:
        task_id: Task this work belongs to.
        conversation_id: Shared namespace.
        agent_name: "dev_worker", "planner", or "chair".
        content: Description of what was done.
        turn_type: "analysis", "implementation", "question", "completion", or "error".
        visibility: "internal" or "external".
    """
    return await _post("/v1/ageix/agent-turns", {
        "task_id": task_id,
        "conversation_id": conversation_id,
        "agent_name": agent_name,
        "content": content,
        "turn_type": turn_type,
        "visibility": visibility,
    })


@mcp.tool()
async def ageix_get_agent_turns(task_id: str) -> dict[str, Any]:
    """Read the full audit trail of agent work on a task.

    Use this to review what Claude Code did before approving a PR.
    """
    return await _get(f"/v1/ageix/tasks/{task_id}/agent-turns")


@mcp.tool()
async def ageix_get_shared_memory(conversation_id: str) -> dict[str, Any]:
    """Read the persistent shared memory for a conversation.

    This is the cross-session context bridge between architect and dev worker.
    """
    return await _get(f"/v1/ageix/conversations/{conversation_id}/summary")


@mcp.tool()
async def ageix_set_shared_memory(conversation_id: str, summary: str) -> dict[str, Any]:
    """Write the persistent shared memory for a conversation.

    Either interface can write here; the other reads it on next session start.
    """
    return await _post(f"/v1/ageix/conversations/{conversation_id}/summary", {
        "summary": summary,
    })


@mcp.tool()
async def ageix_chair_advance(task_id: str) -> dict[str, Any]:
    """Ask the Chair to advance the next unblocked subtask to in_progress.

    The Chair picks the next ready work item and assigns it.
    """
    return await _post(f"/v1/ageix/tasks/{task_id}/chair/advance", {})


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ageix MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport: stdio (Claude Code) or sse (claude.ai, port 8001)",
    )
    args = parser.parse_args()
    mcp.run(transport=args.transport)
