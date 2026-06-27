# Ageix MCP Server Spec

## Purpose

Build an MCP (Model Context Protocol) server inside Ageix that exposes its existing
task/conversation/collaboration APIs as tools. This allows both:

- **claude.ai (architect)** — to read project state, post collaboration turns, review
  agent activity, and assign work without leaving the chat interface
- **Claude Code (dev worker)** — to read its assignments, report progress, post agent
  turns, and pull context from the shared store

Both connect to the **same running Ageix instance** at `http://localhost:8000`. Ageix
becomes the shared brain — persistent state that bridges the two Claude interfaces.

---

## File to Create

`mcp/server.py`

Also create:
- `mcp/__init__.py` (empty)
- `mcp/MCP_SPEC.md` (copy of this file)

---

## Implementation Approach

Use the `mcp` Python SDK (`pip install mcp`). Run the MCP server as a separate process
alongside the FastAPI app — it wraps the Ageix HTTP API via `httpx` rather than importing
directly, so it stays decoupled and works even if FastAPI is on a remote host.

```bash
# Run alongside uvicorn:
python mcp/server.py
```

The MCP server communicates over stdio (standard for Claude Code integration).
For claude.ai, it will need to run as an SSE server — implement both modes with a
`--transport` flag: `stdio` (default) and `sse`.

---

## MCP Tools to Implement

### 1. `ageix_get_project_status`
Read the current state of all active tasks.

**Input:** `conversation_id: str`

**Implementation:** `GET /v1/ageix/tasks` filtered by conversation_id, then for each
top-level task fetch `GET /v1/ageix/tasks/{id}/chair/briefing`

**Returns:** Summary of all tasks, their statuses, progress, and next actions.

**Use case:** Architect opens claude.ai, calls this to immediately understand where
things stand without any manual sync.

---

### 2. `ageix_get_task_tree`
Get the full subtask tree for a parent task.

**Input:** `task_id: str`

**Implementation:** `GET /v1/ageix/tasks/{task_id}/tree`

**Returns:** Nested task tree with statuses.

---

### 3. `ageix_create_task`
Create a new task (architect assigns work).

**Input:**
```json
{
  "conversation_id": "str",
  "title": "str",
  "description": "str",
  "priority": "normal | high | low",
  "owner": "planner | dev_worker | user"
}
```

**Implementation:** `POST /v1/ageix/tasks`

**Returns:** Created task object with task_id.

---

### 4. `ageix_plan_task`
Ask the planner to decompose a task into subtasks.

**Input:** `task_id: str`

**Implementation:** `POST /v1/ageix/tasks/{task_id}/plan`

**Returns:** Parent task + list of created subtasks.

**Use case:** Architect creates a high-level task, then calls this to let Ageix break
it into concrete work items for Claude Code.

---

### 5. `ageix_update_task`
Update task status, owner, or description.

**Input:**
```json
{
  "task_id": "str",
  "status": "todo | in_progress | planned | completed | blocked",
  "owner": "str (optional)",
  "description": "str (optional)"
}
```

**Implementation:** `PATCH /v1/ageix/tasks/{task_id}`

**Use case:** Claude Code marks a task complete; architect unblocks a blocked task.

---

### 6. `ageix_post_collaboration_turn`
Post a structured message from one agent to another.

**Input:**
```json
{
  "conversation_id": "str",
  "speaker": "architect | dev_worker | chair | user",
  "target": "dev_worker | architect | repository | chair",
  "intent": "assignment | question | status_update | review_request | discussion",
  "content": "str"
}
```

**Implementation:** `POST /v1/ageix/collaboration/turns`

**Returns:** Decision + work order result if the turn triggered execution.

**Use case:** This is the primary communication channel. Architect posts an assignment
turn; Claude Code picks it up and posts a status_update turn back.

---

### 7. `ageix_get_collaboration_turns`
Read the conversation history between agents.

**Input:** `conversation_id: str`, `limit: int = 20`

**Implementation:** `GET /v1/ageix/collaboration/{conversation_id}/turns`

**Returns:** Ordered list of turns with speaker, target, intent, content, timestamp.

**Use case:** Claude Code starts a session and reads recent turns to understand its
current assignment without needing manual context paste.

---

### 8. `ageix_post_agent_turn`
Record a unit of agent work (audit trail).

**Input:**
```json
{
  "task_id": "str",
  "conversation_id": "str",
  "agent_name": "dev_worker | planner | chair",
  "content": "str",
  "turn_type": "analysis | implementation | question | completion | error",
  "visibility": "internal | external"
}
```

**Implementation:** `POST /v1/ageix/agent-turns`

**Use case:** Claude Code records what it did — file reads, changes made, decisions —
so the architect can review without needing Claude Code to be running.

---

### 9. `ageix_get_agent_turns`
Read the audit trail of what an agent has done on a task.

**Input:** `task_id: str`

**Implementation:** `GET /v1/ageix/tasks/{task_id}/agent-turns`

**Use case:** Architect reviews Claude Code's work log before approving a PR.

---

### 10. `ageix_get_shared_memory`
Read the conversation summary (shared persistent memory).

**Input:** `conversation_id: str`

**Implementation:** `GET /v1/ageix/conversations/{conversation_id}/summary`

**Returns:** The current summary string.

---

### 11. `ageix_set_shared_memory`
Update the conversation summary (shared persistent memory).

**Input:** `conversation_id: str`, `summary: str`

**Implementation:** `POST /v1/ageix/conversations/{conversation_id}/summary`

**Use case:** Either interface can write key decisions/context here. The other reads it
on next session start. This is the cross-session memory bridge.

---

### 12. `ageix_chair_advance`
Ask the Chair to advance the next ready subtask to in_progress.

**Input:** `task_id: str`

**Implementation:** `POST /v1/ageix/tasks/{task_id}/chair/advance`

**Use case:** Architect tells the Chair to move things forward; Chair picks the next
unblocked task and assigns it.

---

## Claude Code Configuration

After implementing `mcp/server.py`, add to Claude Code's MCP config
(typically `~/.claude/claude_code_config.json` or via `claude mcp add`):

```json
{
  "mcpServers": {
    "ageix": {
      "command": "python",
      "args": ["/path/to/Ageix/mcp/server.py"],
      "env": {
        "AGEIX_BASE_URL": "http://localhost:8000"
      }
    }
  }
}
```

---

## claude.ai Configuration (SSE mode)

When `mcp/server.py` is running in SSE mode (`python mcp/server.py --transport sse`),
add it to claude.ai's MCP settings pointing at:

```
http://localhost:8001/sse
```

(Use port 8001 to avoid collision with FastAPI on 8000.)

---

## Recommended Workflow Once Live

```
1. Architect (claude.ai) calls ageix_get_project_status → sees current state
2. Architect calls ageix_create_task → creates high-level goal
3. Architect calls ageix_plan_task → Ageix decomposes into subtasks
4. Architect calls ageix_post_collaboration_turn (intent: assignment) → assigns to dev_worker
5. Claude Code calls ageix_get_collaboration_turns → reads its assignment
6. Claude Code does the work, calls ageix_post_agent_turn for each step
7. Claude Code calls ageix_update_task (status: completed)
8. Claude Code calls ageix_post_collaboration_turn (intent: review_request)
9. Architect calls ageix_get_agent_turns → reviews the work log
10. Architect approves → Claude Code opens PR via git
11. GitHub App picks up PR → Claude responds to review comments
```

---

## Dependencies to Add

```
mcp>=1.0.0
httpx>=0.27.0
```

Add to your requirements file.

---

## Implementation Notes

- Use `httpx.AsyncClient` for all Ageix API calls (async throughout)
- The `AGEIX_BASE_URL` env var should default to `http://localhost:8000`
- All tools should return clean JSON-serializable dicts, not raw HTTP responses
- Add a `ageix_health` tool that pings `/health` — useful for verifying connectivity
- Error handling: if Ageix is not running, return a clear message rather than crashing
- The `conversation_id` is the shared namespace — architect and dev_worker should use
  the same one. Suggest using the repo name as default: `"ageix-main"`
