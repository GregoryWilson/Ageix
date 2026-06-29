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
services/repo_write_governance_service.py        Sprint-scoped standing grants + single-use one-off
                                                  approvals gating mutating git capabilities
services/repository_git_mutation_service.py      Structured, allowlisted git mutations (fetch, pull,
                                                  checkout, branch, tag, commit, push, push-to-main)
services/capabilities/repository_git_capabilities.py   Registers the 17 repo.* git management
                                                         capabilities (governed_read/governed_write)
services/*  (many more)      One service per governed capability domain — grep services/ for the full list

ageix_mcp/
  server.py                  Builds the governed FastMCP transport (build_fastmcp_server) — auth derived
                              per-request from the Authorization header, delegates to MCPService
  tool_definitions.py         124 MCPToolDefinition entries across 18 categories (architecture, evidence,
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
health.py  logger.py  providers/  config.yaml  safety/  agents/
```

### `legacy_mcp/server.py` — NOT dead code, but a separate legacy bridge still live in production

Despite being the *first* MCP attempt (13 tools wrapping a mostly-dead `/v1/ageix/*`
REST API, with no Authorization header sent on any HTTP call), `legacy_mcp/server.py`
(formerly `mcp/server.py`, renamed to stop shadowing the real `mcp` PyPI package) is
**still actively deployed** — `scripts/Ops/restart_ageix_mcp.sh` runs it as a
standalone FastMCP process on port 8001 (`--transport sse`), reverse-proxied by
nginx at `ageix.wilsongpt.com`. It is architecturally separate from `web/app.py`
(port 8002) and from `ageix_mcp/`, the real governed platform mounted at `/mcp` on
that same process. Because it sends no auth header, calls into the now-auth-required
boundary 401. New tools added to `ageix_mcp/` are invisible to clients using this
bridge no matter how the catalog grows — restarting `web/app.py` does not restart
this separate process, and this process doesn't expose `ageix_mcp/`'s catalog at
all. If you're asked to "test the Ageix MCP capabilities," that still means
`ageix_mcp/`, not `legacy_mcp/server.py`. External MCP connectors (Claude Code on
the web, claude.ai) have since been repointed at the real `/mcp` transport with
OAuth — confirmed working end-to-end (auth + governed capability execution).
`legacy_mcp/server.py` is retained for now pending its decommission
(`scripts/Ops/restart_ageix_mcp.sh stop`) but should no longer be the active path
for new clients.

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
- 124 tools across categories: architecture (37), evidence (13), validation (9),
  patch (8), repository (25), proposal (4), consultation (3), artifact (3),
  artifact_delivery (3), decision_trace (6), agent (2), capability (2), governance (1),
  identity (1), system (1), workflow (1), project (3), audit (1).
- Every governed call is recorded via `CapabilityAuditService` — audit continuity is
  part of the contract, not optional logging.

To test it without a live deployment or network access, run the in-process smoke
test (spins up `web.app:create_app` via `TestClient`, no daemon needed):

```bash
PYTHONPATH=. python scripts/Smoke/smoke_16_4_mcp_transport_bridge.py
```

Note: the local `mcp/` directory used to collide with the real `mcp` PyPI
package (causing `ModuleNotFoundError: No module named 'mcp.types'` and FastMCP
transport construction failures) whenever the repo root landed on `sys.path` ahead
of site-packages, which `uvicorn web.app:app` does by default. Fixed by renaming
the legacy prototype to `legacy_mcp/`; `legacy_mcp/server.py` still defensively
strips the project root from `sys.path` before importing FastMCP — see the comment
at the top of that file.

### Repository git management (`repo.*` capabilities)

Claude Code (and other governed agents) can read and mutate the local git
checkout through 17 `repo.*` capabilities/tools, gated by
`RepoWriteGovernanceService` (`services/repo_write_governance_service.py`):

- **Ungated, read-only/non-destructive:** `repo.fetch`, `repo.tag.list`.
- **Gated mutations** — require either an active sprint grant or a one-off
  human approval: `repo.pull`, `repo.checkout`, `repo.branch.create`,
  `repo.branch.delete`, `repo.tag.create`, `repo.tag.delete`, `repo.commit`,
  `repo.push` (refuses the default branch).
- **`repo.push.main`** — pushing the default branch is its own capability and
  is **never** satisfiable by a sprint grant; it always requires a fresh,
  single-use human approval (`repo.write.approve` with
  `approved_by="human"`), enforced in two independent places (rejected at
  grant-creation time and never consulted by `authorize_mutation` for this
  capability_id).
- **Grant/approval management (human-only):** `repo.write.grant.create`,
  `repo.write.grant.revoke`, `repo.write.grant.list`, `repo.write.approve`,
  `repo.write.approval.list`. `create_grant`/`create_approval` raise
  `PermissionError` unless the caller-supplied identity literally equals the
  string `"human"`.
- Underlying git mutations run through `RepositoryGitMutationService`
  (`services/repository_git_mutation_service.py`): structured method calls
  only (no raw command strings), regex-validated ref names, repo-relative
  path validation for commit staging, and a hardcoded allowlist of git
  subcommands. No force-push or force-branch-delete is exposed in this
  version. This is a separate, additive governance primitive — it does not
  modify or relax the existing `GovernancePolicyService`/`ControlsService`
  locks, which gate a different consumer (the autonomous repair loop).
- A local sandbox for testing mutations before they touch the real working
  copy is deferred to a future phase.

Run `pytest tests/test_sprint_20_0_repository_git_governance.py` or
`PYTHONPATH=. python scripts/Smoke/smoke_20_0_repository_git_governance.py`
to exercise the grant/approval flows end to end.

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
