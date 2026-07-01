# Sprint 26.2.5 — Open WebUI Adapter Registration Validation

Project: Ageix  
Branch: `sprint-26-2-5-open-webui-adapter-registration`  
Base used: `sprint-26-2-decision-inbox-mvp` because GitHub `main` does not yet contain the Sprint 26.2 Decision Inbox endpoint files required by this sprint.  
Status: implementation validation artifact

## Objective

Wire the existing Sprint 26.2 Human Interface Decision Inbox endpoint into Open WebUI as a read-only Ageix surface by adding the minimum OpenAPI registration artifact, usage documentation, and smoke validation required for Open WebUI-compatible access.

## Repository evidence inspected

The existing Sprint 26.2 endpoint was inspected before implementation:

- `human_interface_adapter.py`
  - Defines `APIRouter(prefix="/human-interface", tags=["human-interface"])`.
  - Exposes `GET /human-interface/decision-inbox`.
  - Requires an `Authorization` header before returning governed records.
  - Delegates project enforcement and read-only projection behavior to `HumanInterfaceDecisionInboxService`.
- `human_interface_gateway.py`
  - Defines `FastAPI(title="Ageix Human Interface Adapter")`.
  - Includes the Human Interface Adapter router.
  - Provides the FastAPI-generated OpenAPI document at `/openapi.json` when the adapter is running.
- `services/human_interface_decision_inbox_service.py`
  - Requires `project_id == "Ageix"`.
  - Returns `project_id_required` when project context is missing.
  - Returns `project_scope_denied` when project context is incorrect.
  - Returns read-only summary-first records from existing Ageix stores.
  - Does not create approval state, trigger workers, call capability execution, write audit records, mutate proposals, ADRs, evidence, validation files, decision traces, Git, or architecture registry data.
- `tests/test_human_interface_decision_inbox.py`
  - Covers missing project context denial.
  - Covers incorrect project context denial.
  - Covers missing authorization denial.
  - Covers summary-first traceable read-only shape.
  - Covers absence of executable mutation controls.
  - Covers no file mutation during reads.

## Selected Open WebUI path

Selected path: OpenAPI tool-server registration.

Rationale:

- FastAPI already exposes an OpenAPI-compatible surface for the Ageix-owned Human Interface Adapter.
- The required endpoint is read-only and maps cleanly to a single OpenAPI `GET` operation.
- No Open WebUI plugin, pipeline, function, filter, custom Python, or unfinished intent engine dependency is required.
- Authorization, project scope, state ownership, and governance remain inside Ageix.

MCP Streamable HTTP was not selected because it is unnecessary for this narrow read-only registration sprint.

## Files added

- `open_webui/decision_inbox_openapi.json`
  - Static OpenAPI registration artifact for review/manual registration.
  - Exposes only `GET /human-interface/decision-inbox`.
  - Requires bearer authorization.
  - Requires explicit `project_id=Ageix` query context through OpenAPI parameter metadata.
- `docs/open_webui_decision_inbox_registration.md`
  - Documents Greg-facing Open WebUI registration and smoke-use instructions.
  - Documents expected denial behavior for missing auth, missing project context, and incorrect project context.
- `tests/test_open_webui_decision_inbox_registration.py`
  - Validates FastAPI-generated OpenAPI exposes the Decision Inbox path as GET-only.
  - Validates the static OpenAPI registration artifact is read-only and Open WebUI-compatible.
  - Validates explicit Ageix project context metadata.
  - Validates missing authorization, missing project context, and incorrect project context fail safely.
  - Validates authorized read remains read-only and exposes no prohibited mutation fragments.

## Read-only and governance validation

Confirmed by implementation design and tests:

- Only a `GET` operation is registered.
- `project_id=Ageix` remains explicit.
- Missing `project_id` remains denied.
- Incorrect `project_id` remains denied.
- Missing authorization remains denied.
- Open WebUI stores no approval state.
- No approval, reject, defer, request-changes, rationale/comment mutation, worker trigger, repository mutation, Open WebUI plugin, Open WebUI pipeline, or intent-engine dependency was introduced.

## Recommended validation commands

Run from repository root on the completed branch:

```bash
pytest tests/test_human_interface_decision_inbox.py tests/test_open_webui_decision_inbox_registration.py
```

Optional endpoint smoke after starting the adapter:

```bash
curl -sS http://localhost:8000/openapi.json | jq '.paths["/human-interface/decision-inbox"].get.operationId'

curl -sS \
  -H "Authorization: Bearer $AGEIX_TOKEN" \
  "http://localhost:8000/human-interface/decision-inbox?project_id=Ageix" \
  | jq '.summary.mode, .read_only, .summary.mutation_controls_exposed'
```

Expected values for authorized read:

```text
"read_only"
true
false
```

## Validation status

Implementation artifacts were added through the GitHub connector. Runtime test execution was not available inside the connector session. The exact commands above should be run locally or through the governed validation runner after checking out `sprint-26-2-5-open-webui-adapter-registration`.

## Regression summary

Expected regression risk is low. The sprint adds registration/configuration, documentation, and focused tests only. It does not modify the existing Decision Inbox service, route, router inclusion, authorization behavior, or Ageix system-of-record stores.
