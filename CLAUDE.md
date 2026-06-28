# Ageix — Claude Code Context

## What This Project Is

Ageix is a **local-first AI gateway** built in Python/FastAPI. It routes prompts between
local models (Ollama) and cloud models (OpenRouter) based on keyword-driven routing rules,
and orchestrates multi-agent workflows through a structured task/work-order system.

The project is also its own development environment — Ageix is being used to build Ageix.
Claude Code is the primary dev worker. The claude.ai chat interface acts as architect.
Ageix itself is the shared state layer that connects them.

## Architecture Overview

```
app.py              FastAPI entrypoint — all HTTP routes live here (904 lines)
router.py           Prompt routing logic (local vs cloud)
config.yaml         Provider config: Ollama @ 192.168.68.56:11434, OpenRouter
store.py            SQLite persistence — conversations, messages, tasks, agent turns
planner.py          Breaks tasks into subtasks via LLM
chair.py            PMO coordinator — advances tasks, produces briefings
work_order.py       WorkOrder dataclass — the unit of work dispatched to agents
work_order_runner.py Executes work orders against the agent registry
collaboration_turn.py  CollaborationTurn model — structured agent-to-agent messages
collaboration_router.py Routes collaboration turns to the right agent
evaluator_agent.py  Evaluates agent output quality
artifact_store.py   Stores agent-produced artifacts
health.py           /health endpoint
logger.py           Logging
```

### Key Subdirectories
```
agents/             Agent implementations (planner_agent.py confirmed)
llm/                LLM client layer (router.py, schemas.py)
providers/          Provider adapters (ollama.py, openrouter.py)
safety/             Input scrubbing (scrubber.py)
schemas/            Pydantic/data schemas
services/           Service layer
tools/              Tool implementations
prompts/            Prompt templates
contracts/          Interface contracts
tests/              pytest test suite (pytest.ini at root)
scratch/            Scratchpad/experiments
.ageix/             Ageix internal config
```

## Models in Use

| Key              | Provider    | Model                        |
|------------------|-------------|------------------------------|
| local_fast       | Ollama      | qwen3:8b                     |
| local_reasoning  | Ollama      | qwen3:8b                     |
| local_coding     | Ollama      | deepseek-coder-v2            |
| cloud_fast       | OpenRouter  | openai/gpt-4o-mini           |
| cloud_reasoning  | OpenRouter  | anthropic/claude-sonnet-4    |
| cloud_coding     | OpenRouter  | openai/gpt-5                 |

Cloud routing triggers on keywords: architecture, complex, deep reasoning, design,
strategy, analyze, code, debug, programming.

## Core API Patterns

All Ageix-specific routes are under `/v1/ageix/`. OpenAI-compatible routes at `/v1/`.

**Tasks** — full CRUD with parent/child tree, planning, and status:
- `POST /v1/ageix/tasks` — create
- `GET /v1/ageix/tasks/{id}/tree` — full subtask tree
- `POST /v1/ageix/tasks/{id}/plan` — LLM-driven subtask decomposition
- `POST /v1/ageix/tasks/{id}/chair/advance` — Chair advances next subtask
- `GET /v1/ageix/tasks/{id}/chair/briefing` — Chair status briefing
- `POST /v1/ageix/tasks/{id}/run` — Execute planner agent on task

**Collaboration** — structured agent-to-agent turns:
- `POST /v1/ageix/collaboration/turns` — post a CollaborationTurn
- `GET /v1/ageix/collaboration/{conversation_id}/turns` — read turn history

**Conversations** — persistent memory:
- `POST /v1/ageix/conversations/{id}/messages` — send message, get routed response
- `GET /v1/ageix/conversations/{id}/messages` — history
- `POST /v1/ageix/conversations/{id}/summary` — update summary (shared memory)
- `GET /v1/ageix/conversations/{id}/summary` — read summary

**Agent Turns** — audit trail of agent activity:
- `POST /v1/ageix/agent-turns` — record an agent turn
- `GET /v1/ageix/tasks/{id}/agent-turns` — read all turns for a task

## The WorkOrder Pattern

WorkOrders are the unit of autonomous work:
```python
WorkOrder(
    work_order_id: str,
    agent: str,           # e.g. "dev_worker", "planner", "repository"
    objective: str,
    instructions: list[str],
    input_artifacts: list[str],
    deliverable: dict,    # schema of expected output
    success_criteria: list[str],
    constraints: dict,    # e.g. {"no_file_writes": True}
)
```

## Active Development Focus

**Next major feature: MCP Server (`legacy_mcp/server.py`)**

Goal: expose Ageix's task/conversation/collaboration APIs as MCP tools so that both
Claude Code (terminal) and claude.ai (browser) can connect to the same running Ageix
instance as a shared state layer. This bridges the two interfaces without manual
copy-paste.

See `mcp/MCP_SPEC.md` for the full tool spec (to be created).

## Conventions

- Python with FastAPI + Pydantic
- SQLite via `store.py` for all persistence (no ORM)
- All new agents go in `agents/`
- All new providers go in `providers/`
- Tests go in `tests/` and run with `pytest`
- Don't break the OpenAI-compatible `/v1/chat/completions` route
- `config.yaml` is the single source of truth for model/provider config
- WorkOrder constraints with `"no_file_writes": True` mean proposal-only mode

## Running Locally

```bash
# Assumes venv is active and dependencies installed
uvicorn app:app --reload --port 8000
```

Ollama is on a separate host at `192.168.68.56:11434`.

## Key Relationships

```
User/Architect (claude.ai)
        │
        │  MCP tools (planned)
        ▼
  Ageix Gateway (FastAPI @ :8000)  ◄──► SQLite store
        │
        │  MCP tools (planned)
        ▼
Claude Code (terminal dev worker)
        │
        │  git commits / PRs
        ▼
   GitHub repo (GregoryWilson/Ageix)
        │
        │  GitHub App trigger
        ▼
  Claude GitHub App (PR/issue automation)
```
