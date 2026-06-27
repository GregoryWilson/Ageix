# Ageix — Claude Code Context

## What This Project Is

Ageix is a **governed multi-agent platform**. It started as a simple local/cloud LLM
routing gateway, but that prototype is now dead code — the live system is a FastAPI
service (`web/app.py`, "Ageix Governed Service Boundary") that exposes projects,
proposals, consultations, architecture review, and a governed MCP capability surface
to external agent clients (Claude, ChatGPT, etc.) over OAuth.

The project is also its own development environment — Ageix is being used to build
Ageix. Claude Code is the primary dev worker; claude.ai/connected agents act as
architect/consultants through the governed MCP boundary described below.

## Architecture Overview — current (live)

```
web/app.py                 FastAPI factory: create_app() — "Ageix Governed Service Boundary"
web/routes/
  oauth_discovery_routes.py  /.well-known/oauth-protected-resource, /oauth-authorization-server, /openid-configuration
  health_routes.py           GET /health
  capability_routes.py       GET /capabilities, POST /capabilities/execute
  project_routes.py          GET /projects/current
  proposal_routes.py         POST/GET /proposals, GET /proposals/{id}
  consultation_routes.py     POST /consultations, GET /consultations/{id}
  audit_routes.py            GET /audit/recent
  mcp_routes.py               /mcp/tools, /mcp/tools/call  (REST-governed MCP discovery + execution)
web/auth.py                 Bearer-token auth dependency -> AuthService
web/mcp_transport.py        Mounts the FastMCP transport app at /mcp (ageix_mcp/server.py)

services/auth_service.py    Resolves caller identity from bearer token; OAuth (Keycloak) or dev-token modes
services/auth_providers/    jwt_provider.py (OAuth/JWT), dev_token_provider.py (static tokens — see Auth below)
services/mcp_service.py     Executes governed MCP tool calls; enforces capability authorization + audit
services/capability_*.py    Capability registry, execution, security/authorization services
services/chair_*.py         Chair governance/decision services
services/architecture_*.py  Architecture registry/baseline/revision services (ARCH-* nodes under .ageix/architecture/)
services/proposal_*.py      Proposal orchestration, refinement, quality, promotion-readiness
services/consultation_*.py  Consultation session + evidence review services
services/*  (many more)      One service per governed capability domain — grep services/ for the full list

ageix_mcp/
  server.py                  Builds the governed FastMCP transport (build_fastmcp_server) — auth derived
                              per-request from the Authorization header, delegates to MCPService
  tool_definitions.py         107 MCPToolDefinition entries across 18 categories (architecture, evidence,
                              validation, patch, repository, proposal, consultation, audit, identity,
                              capability, system, agent, artifact, artifact_delivery, decision_trace,
                              governance, workflow, project)
  tool_registry.py            MCPToolRegistry — capability_id mapping, discovery, listing
  clients/                    client_registry.py, client_admission_policy.py, client_trust_validator.py —
                              per-client (claude, chatgpt, ...) admission/trust rules
  discovery_service.py, facade_service.py

.ageix/
  config/auth.json            Auth config: auth_enabled, mode, OAuth issuer (Keycloak), allowed projects
  architecture/                Architecture nodes/ADRs/principles/intents — the governed architecture graph
  projects/, proposals/, decision_traces/, patches/, verification/, ...   Governed state, written by services/

models/, schemas/             Pydantic models (AuthIdentity, AgeixRequestContext, MCPEnvelope, etc.)
tests/test_sprint_*.py        pytest suite, one file per sprint/feature — run with pytest
scripts/Ops/*.sh              restart_ageix.sh, provision_mcp_client.sh, verify_mcp_client_oauth.sh, ...
scripts/Smoke/smoke_*.py      In-process smoke tests (FastAPI TestClient) — no live server/network needed
docs/runbooks/ageix_service_operations.md   Operational runbook (start/stop, auth refresh, MCP validation)
```

### Legacy / dead code — do not treat as current

These root-level files are the **original simple prototype** (untouched since the
initial commit). Nothing under `web/`, `services/`, or `ageix_mcp/` imports them.
They are not wired into the running app and should not be used as a reference for
current behavior:

```
app.py  router.py  store.py  chair.py  planner.py  work_order.py  work_order_runner.py
collaboration_turn.py  collaboration_router.py  evaluator_agent.py  artifact_store.py
health.py  logger.py  providers/  config.yaml  safety/  mcp/server.py  MCP_SPEC.md
agents/
```

`mcp/server.py` and `MCP_SPEC.md` specifically were the *first* MCP attempt (13 simple
tools wrapping a `/v1/ageix/*` REST API that no longer exists). The real MCP platform
is `ageix_mcp/` — see below. If you're asked to "test the Ageix MCP capabilities,"
that means `ageix_mcp/`, not `mcp/server.py`.

## Auth

OAuth via Keycloak is the only auth path for external MCP clients (Claude, ChatGPT,
and any future connector). The dev-token method for external clients has been
**completely eliminated** — there is no shared static token used to authenticate
agent identity anymore. Clients go through Dynamic Client Registration and the
standard OAuth discovery endpoints (`/.well-known/oauth-protected-resource/mcp`,
`/.well-known/oauth-authorization-server/mcp`), provisioned via
`scripts/Ops/provision_mcp_client.sh` and verified via
`scripts/Ops/verify_mcp_client_oauth.sh <client_id>`.

`services/auth_providers/dev_token_provider.py` and the `dev_token`/`hybrid` auth
modes still exist in code as a fallback path used by local smoke tests and an
internal chair-scoped admin token (`.ageix/config/auth.json` → `chair-admin-token`,
read from `AGEIX_CHAIR_ADMIN_TOKEN`) — that's an internal service credential for the
Chair process, not an external-client auth method, and should not be reintroduced as
a way for agents to authenticate.

Config lives at `.ageix/config/auth.json`: `auth_enabled`, `mode`, OAuth issuer
(`https://auth.wilsongpt.com/realms/ageix`), `allowed_projects`.

## The Governed MCP Platform (`ageix_mcp/`)

- Transport: FastMCP, mounted at `/mcp` on `web/app.py` (`web/mcp_transport.py`).
- Every tool call resolves identity from the request's `Authorization: Bearer`
  header via `AuthService`, builds an `AgeixRequestContext`, checks
  `identity.capability_allowed(capability_id)`, then delegates to
  `MCPService.execute_tool` — capability authorization, project authorization,
  Chair governance, and audit logging are enforced centrally, not per-tool.
- REST-governed discovery/execution also exists at `GET /mcp/tools` and
  `POST /mcp/tools/call` (used by `scripts/Smoke/smoke_16_4_mcp_transport_bridge.py`)
  for clients that prefer plain HTTP over the FastMCP stdio/SSE transport.
- 107 tools across categories: architecture (37), evidence (13), validation (9),
  patch (8), repository (8), proposal (4), consultation (3), artifact (3),
  artifact_delivery (3), decision_trace (6), agent (2), capability (2), governance (1),
  identity (1), system (1), workflow (1), project (3), audit (1).
- Every governed call is recorded via `CapabilityAuditService` — audit continuity is
  part of the contract, not optional logging.

To test it without a live deployment or network access, run the in-process smoke
test (spins up `web.app:create_app` via `TestClient`, no daemon needed):

```bash
PYTHONPATH=. python scripts/Smoke/smoke_16_4_mcp_transport_bridge.py
```

Note: importing the real `mcp` PyPI package while `PYTHONPATH=.` is set can get
shadowed by the local `mcp/` directory (the legacy prototype) — see the workaround
comment at the top of `mcp/server.py` if you hit `ModuleNotFoundError: No module
named 'mcp.types'`.

## Running Locally

The live entrypoint is `web.app:create_app`, **not** root `app.py`:

```bash
PYTHONPATH=. ./venv/bin/uvicorn web.app:create_app --factory --host 127.0.0.1 --port 8002
```

Or use the managed script, which also polls `/health` until ready:

```bash
scripts/Ops/restart_ageix.sh start   # or: stop / restart (default)
```

Defaults to `127.0.0.1:8002`. Logs to `/tmp/ageix_uvicorn.log`. See
`docs/runbooks/ageix_service_operations.md` for auth-refresh validation and MCP
publication checks after changes.

## Conventions

- Python with FastAPI + Pydantic, one service per governed capability domain under
  `services/`
- New governed MCP tools: add an `MCPToolDefinition` in `ageix_mcp/tool_definitions.py`
  and a backing capability in the relevant `services/*_service.py` / capability registry
- Tests go in `tests/test_sprint_*.py`; smoke tests (no network, `TestClient`-based) go
  in `scripts/Smoke/`
- Don't reintroduce a static/dev-token auth path for external MCP clients — OAuth via
  Keycloak is the only supported method now
- `.ageix/` holds governed runtime state (architecture graph, proposals, audit, config)
  — much of it is written by services at runtime, not hand-edited

## Key Relationships

```
External agent client (Claude, ChatGPT, ...)
        │
        │  OAuth (Keycloak: auth.wilsongpt.com) + Dynamic Client Registration
        ▼
  ageix_mcp/ governed MCP transport, mounted at /mcp
        │
        ▼
  web/app.py (Ageix Governed Service Boundary, :8002)
        │
        ▼
  services/  (capability execution, Chair governance, architecture, proposals, audit)
        │
        ▼
  .ageix/  (governed state on disk)
        │
        │  git commits / PRs
        ▼
   GitHub repo (GregoryWilson/Ageix)
        │
        │  GitHub App trigger
        ▼
  Claude GitHub App (PR/issue automation)
```
