# Sprint 26.1 — Open WebUI Integration Spike Validation

Project: Ageix  
Branch: `sprint-26-1-open-webui-integration-spike`  
Scope: architecture/supporting artifacts only  
Status: validation evidence  

## Branch basis

Sprint 26.0 was not present on `main` at inspection time. The Sprint 26.0 Human Interface artifacts existed on PR #3, branch `sprint-26-human-interface-architecture`, with PR state `open` and `merged=false`.

To preserve traceability to Sprint 26.0 artifacts, Sprint 26.1 was branched from `sprint-26-human-interface-architecture` rather than from `main`.

## Repository inspection performed

Confirmed via GitHub connector:

- Repository: `GregoryWilson/Ageix`
- Default branch: `main`
- Sprint 26.0 PR: `#3`, `Sprint 26.0 — Human Interface Architecture Foundation`
- Sprint 26.0 PR branch: `sprint-26-human-interface-architecture`
- Sprint 26.0 PR status: open, not merged
- Sprint 26.1 branch created: `sprint-26-1-open-webui-integration-spike`

Inspected repository artifacts:

- `.ageix/architecture/human_interface_architecture.json`
- `.ageix/architecture/human_interface_foundation.md`
- `.ageix/architecture/validation/sprint_26_human_interface_validation.md`
- `.ageix/architecture/index.json`

Repository evidence summary:

- Sprint 26.0 defines `ARCH-AGEIX-HUMANINTERFACE` as proposed architecture only.
- Sprint 26.0 defines `ARCH-AGEIX-HUMANINTERFACE-INTERACTIONSHELL` for Open WebUI and future shell boundaries.
- Sprint 26.0 defines `ARCH-AGEIX-HUMANINTERFACE-GOVERNEDINTERACTIONADAPTER` as the adapter boundary between shells and governed Ageix capabilities.
- Sprint 26.0 forbids direct UI-to-worker mutation, direct governance bypass, and separate approval authority.
- The canonical architecture index contains existing platform IDs referenced by the Sprint 26.0 Human Interface artifacts.

## AgeixAI inspection performed

All AgeixAI operations explicitly used `project_id: "Ageix"`.

Confirmed:

- `EVPKG-298023C1EE14` is active and fresh according to `ageix.evidence.package.details`.
- `ADR-1CE374A025B2` resolves to `ADR-0017` and states that Open WebUI is the initial Ageix Human Interface shell while Ageix-specific governance remains inside Ageix.
- `PRIN-0007` is available through the principles list as `ARCHPRIN-2723697A4693` and states that human interfaces must not bypass governance.
- `INTENT-0008` is available through the intents list as `ARCHINTENT-0A4B1C8668A5` and prioritizes governance workflows before conversation workflows.
- `ARCHREV-2F16C935631A` was retrieved and records the Phase 26 Human Interface validation plan.

Partial / unavailable:

- Direct lookup by display number `ADR-0017` returned not found; canonical lookup by `ADR-1CE374A025B2` succeeded.
- Direct lookup by display number `PRIN-0007` returned not found; listing resolved the canonical principle record.
- Direct lookup by display number `INTENT-0008` returned not found; listing resolved the canonical intent record.

## Open WebUI evidence inspected

Primary/current Open WebUI documentation inspected:

- `https://docs.openwebui.com/`
- `https://docs.openwebui.com/features/extensibility/plugin/`
- `https://docs.openwebui.com/features/extensibility/mcp/`
- `https://docs.openwebui.com/features/authentication-access/`
- `https://docs.openwebui.com/features/authentication-access/rbac/`
- `https://docs.openwebui.com/features/authentication-access/api-keys/`
- `https://docs.openwebui.com/getting-started/essentials/`

Open WebUI evidence summary:

- Open WebUI provides extensibility through Tools, Functions, Pipes, Filters, Actions, Pipelines, MCP, and OpenAPI-style tool-server connections.
- Open WebUI documentation warns that Tools, Functions, Pipes, Filters, and Pipelines execute arbitrary Python code on the server.
- Open WebUI supports SSO/OIDC and RBAC, but Open WebUI RBAC governs Open WebUI access only and does not replace external provider or Ageix authorization.
- Open WebUI supports MCP Streamable HTTP servers and OAuth 2.1 / OAuth 2.1 Static configuration for MCP connections.
- Open WebUI custom header templates can propagate user/chat/message metadata to external tool servers, but those values are correlation inputs only and not Ageix authority.
- Open WebUI API keys inherit the creating user's permissions and are not a replacement for Ageix capability authorization.

## Validation checks

| Check | Result | Evidence |
|---|---:|---|
| Repository inspection preceded recommendations | PASS | Repo metadata, PR #3, Sprint 26.0 artifacts, and architecture index were inspected before writing 26.1 artifacts. |
| Sprint 26.0 artifacts referenced | PASS | 26.1 artifacts reference and build on Sprint 26.0 Human Interface architecture files. |
| AgeixAI operations used `project_id: "Ageix"` | PASS | Evidence, ADR, principle, intent, and architecture review calls all used project `Ageix`. |
| Open WebUI extension mechanisms assessed | PASS | Tools, Functions, Pipes, Filters, Actions, Pipelines, MCP, OpenAPI, custom UI/page feasibility, admin/workspace limits assessed. |
| Auth/session boundary assessed | PASS | OIDC/SSO, RBAC, API keys, OAuth/MCP, session propagation, project context, and unauthorized fallback documented. |
| Adapter pattern identified | PASS | Ageix-owned OpenAPI-first Human Interface Adapter recommended, optionally MCP second. |
| No dependency on unfinished intent engine introduced | PASS | 26.2 recommendation uses deterministic read endpoints and explicit project context. |
| No hard coupling to chat interface introduced | PASS | 26.2 recommendation is structured read-only Decision Inbox, not model/tool-call mediated approval. |
| No direct mutation path introduced | PASS | Only architecture/supporting files were created. No runtime code, worker trigger, Git write path, or approval action was added. |
| No arbitrary shell execution introduced | PASS | No Open WebUI plugin, pipeline, shell, or executable code was added. |
| Ageix remains system of record | PASS | Assessment and adapter pattern explicitly preserve Ageix ownership of proposals, decisions, evidence, validation, workers, audit, and governance. |
| Production UI not built | PASS | No UI implementation files were added. |

## Files created

- `.ageix/architecture/open_webui_integration_assessment.md`
- `.ageix/architecture/open_webui_adapter_pattern.json`
- `.ageix/architecture/validation/sprint_26_1_open_webui_integration_validation.md`

## Runtime validation

No runtime tests were executed because this sprint is architecture/supporting-artifact only and no executable Ageix or Open WebUI code was changed.

Recommended follow-up validation before Sprint 26.2 implementation:

1. Rebase or recreate Sprint 26.1 after Sprint 26.0 PR #3 is merged, if Greg wants all Phase 26 branches based directly on `main`.
2. Run existing architecture baseline validation after merge.
3. For 26.2, validate that Decision Inbox endpoints are read-only and require `project_id: "Ageix"`.
4. For 26.2, validate unauthorized-user fallback before exposing any Open WebUI surface.
5. For 26.2, validate that no Open WebUI approval state, worker trigger state, or repository mutation path exists.

## Recommendation validation result

Sprint 26.2 can proceed safely if limited to a read-only Decision Inbox surfaced through an Ageix-owned adapter.

Sprint 26.2 should not proceed as approval actions, worker triggers, notification actions, Open WebUI custom plugin installation, or Open WebUI-owned decision state.
