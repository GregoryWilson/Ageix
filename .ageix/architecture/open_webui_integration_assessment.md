# Sprint 26.1 — Open WebUI Integration Assessment

Project: Ageix  
Branch: `sprint-26-1-open-webui-integration-spike`  
Scope: architecture/supporting artifact only  
Status: proposed spike assessment  
Base branch: `sprint-26-human-interface-architecture` because Sprint 26.0 PR #3 was open and not merged into `main` at inspection time.

## Objective

Determine whether Open WebUI can safely host Ageix-specific human interface surfaces for governed decision review, approvals, feedback, and manual workflow initiation without bypassing Ageix governance.

This artifact does not build production UI, approval actions, notification behavior, worker triggers, repository mutation, or Open WebUI runtime code.

## Governing inputs

This assessment is governed by the Sprint 26.0 Human Interface architecture foundation and the following Ageix references:

- `EVPKG-298023C1EE14`
- `ADR-0017` / `ADR-1CE374A025B2`
- `PRIN-0007`
- `INTENT-0008`
- `ARCHREV-2F16C935631A`
- `.ageix/architecture/human_interface_architecture.json`
- `.ageix/architecture/human_interface_foundation.md`
- `.ageix/architecture/validation/sprint_26_human_interface_validation.md`

Key inherited constraints:

- Open WebUI is an interaction shell only.
- Ageix remains the system of record.
- Human-facing state changes must route through governed Ageix capabilities.
- No direct UI-to-worker mutation path is allowed.
- No direct UI-to-repository mutation path is allowed.
- No separate Open WebUI approval store or authority model is allowed.

## Repository evidence inspected

Repository inspection preceded recommendations.

- `GregoryWilson/Ageix` default branch is `main`.
- Sprint 26.0 exists as PR #3, branch `sprint-26-human-interface-architecture`, state `open`, not merged.
- Sprint 26.0 artifacts were inspected from the PR branch.
- `.ageix/architecture/human_interface_architecture.json` defines `ARCH-AGEIX-HUMANINTERFACE` and child components including `InteractionShell`, `GovernedInteractionAdapter`, `DecisionReview`, and `NotificationIntake`.
- `.ageix/architecture/human_interface_foundation.md` defines Open WebUI as presentation/input shell only and forbids direct mutation of DevJobs, workers, architecture, validation, evidence, or governance state.
- `.ageix/architecture/validation/sprint_26_human_interface_validation.md` records Sprint 26.0 validation and confirms no executable UI code was introduced.
- `.ageix/architecture/index.json` was inspected to confirm existing platform architecture IDs, including `ARCH-AGEIX-PROJECT`, `ARCH-AGEIX-WEBPLATFORM`, `ARCH-AGEIX-GOVERNANCEPLATFORM`, `ARCH-AGEIX-SESSIONPLATFORM`, `ARCH-AGEIX-SECURITYPLATFORM`, `ARCH-AGEIX-MCPPLATFORM`, `ARCH-AGEIX-WORKERPLATFORM`, `ARCH-AGEIX-EVIDENCEPLATFORM`, and `ARCH-AGEIX-VALIDATIONPLATFORM`.

## Open WebUI evidence inspected

Primary/current Open WebUI documentation was inspected for extension, auth, MCP, and administrative constraints.

- Open WebUI describes itself as an extensible, self-hosted AI platform supporting Ollama and OpenAI-compatible APIs.
- Open WebUI extension points include Tools, Functions, Pipes, Filters, Actions, Pipelines, MCP server connections, OpenAPI tool servers, and admin-configurable settings.
- Open WebUI documentation explicitly warns that Tools, Functions, Pipes, Filters, and Pipelines execute arbitrary Python code on the server and recommends installing only trusted/reviewed code.
- Tools are generally workspace/model abilities; Functions are admin-managed platform customizations; Pipelines are advanced API-compatible processing surfaces.
- MCP support exists for Streamable HTTP MCP servers and is admin-gated. Open WebUI also documents OAuth 2.1 and OAuth 2.1 Static support for MCP tool-server connections.
- Open WebUI supports SSO/OIDC, LDAP, SCIM, RBAC, groups, per-resource ACLs, and API keys. Open WebUI RBAC is additive and governs Open WebUI behavior, not external provider least privilege.
- Open WebUI custom-header templating can propagate user/chat/message metadata such as user ID, user name, user email, user role, chat ID, and message ID to external tool servers.
- Open WebUI API keys inherit the creating user's permissions and do not provide a separate per-key permission model beyond optional endpoint restrictions.

Primary documentation references:

- `https://docs.openwebui.com/`
- `https://docs.openwebui.com/features/extensibility/plugin/`
- `https://docs.openwebui.com/features/extensibility/mcp/`
- `https://docs.openwebui.com/features/authentication-access/`
- `https://docs.openwebui.com/features/authentication-access/rbac/`
- `https://docs.openwebui.com/features/authentication-access/api-keys/`
- `https://docs.openwebui.com/getting-started/essentials/`

## Assessment by investigation area

### 1. Extension and customization mechanisms

| Mechanism | Feasibility for Ageix | Governance assessment | Recommendation |
|---|---|---|---|
| Tools | Feasible for chat-triggered or model-triggered capability calls. | Risky for approvals because tool invocation may be model-mediated and chat-coupled. | Use only for non-mutating reads or carefully constrained user-initiated review helpers. Do not use as approval authority. |
| Functions / Actions | Feasible for admin-managed UI behavior such as buttons or request/response hooks. | High risk because arbitrary Python executes inside Open WebUI and can drift across upgrades. | Avoid for production mutation paths. Consider only disposable, reviewed, non-mutating spike code. |
| Pipes / Filters | Feasible for model routing, request/response filtering, observability, and formatting. | Not appropriate for Decision Inbox or approvals; may obscure governance semantics. | Do not use for Ageix approval or worker workflow initiation. |
| Pipelines | Feasible for advanced OpenAI-compatible workflow processing. | High operational and arbitrary-code risk; not necessary for 26.2. | Do not use for 26.2 Decision Inbox. Revisit only if a future bounded API transformation requires it. |
| MCP server connection | Feasible for connecting Open WebUI to Ageix governed MCP surface. | Acceptable if Ageix remains the authorizer/system of record and Open WebUI is only a client shell. | Acceptable for read-only capability discovery/review. Mutations require explicit Ageix governance and rationale capture. |
| OpenAPI tool server | Feasible for an Ageix Human Interface Adapter exposing narrow HTTP endpoints. | Stronger fit than arbitrary plugin code; easier to secure, audit, version, and test. | Preferred integration surface for structured Decision Inbox reads and future explicit mutation requests. |
| Custom UI/page/plugin | Possible only through core modification, plugin behavior, or external hosted pages linked/embedded from Open WebUI. | Fragile if implemented inside Open WebUI; risk of hard coupling to chat and upgrade churn. | Prefer Ageix-hosted pages or adapter-served structured surfaces; Open WebUI should link/launch/display, not own. |
| Admin panel / workspace | Useful for configuration, tool-server registration, RBAC, and scoping. | Open WebUI admin/RBAC must not become Ageix authority. | Use for shell access control only. Enforce all Ageix authority inside Ageix. |

### 2. Authentication and session boundary

Open WebUI can participate in an Ageix-safe auth boundary, but it should not define Ageix authorization.

Recommended boundary:

1. Human user authenticates to Open WebUI through OIDC/SSO, preferably the same Keycloak/IdP family used by Ageix.
2. Open WebUI shell access is controlled by Open WebUI RBAC/groups.
3. Open WebUI calls the Ageix Human Interface Adapter through OpenAPI or Streamable HTTP MCP.
4. The adapter validates the caller using Ageix-compatible credentials, claims, or gateway-injected identity.
5. The adapter constructs an Ageix request context with:
   - `project_id: "Ageix"`
   - authenticated user identity
   - Open WebUI user metadata when available
   - Open WebUI chat/message IDs only as supplemental correlation fields
   - explicit user-provided rationale for future state-changing requests
6. Ageix governed capability authorization makes the final allow/deny decision.
7. Unauthorized users receive read-denied or action-denied responses without fallback mutation paths.

Session propagation guidance:

- Treat Open WebUI session IDs and chat IDs as correlation metadata, not Ageix sessions of authority.
- Ageix session context must be created or resolved by the adapter/Ageix boundary.
- Project context must be explicit and pinned to `project_id: "Ageix"` for Ageix-specific surfaces.
- Do not infer project authority from Open WebUI workspace, group, model, chat, or tool selection.

Unauthorized-user fallback:

- Show no privileged decision contents.
- Do not offer approval/rejection/manual trigger controls.
- Provide a safe access-denied message.
- Log denied access through Ageix where the request crosses the Ageix boundary.
- Do not create pending approvals or local Open WebUI placeholders.

### 3. Adapter pattern

Recommended pattern: **Ageix-owned Human Interface Adapter, exposed as narrow OpenAPI first, optionally MCP second.**

Placement decision:

| Placement | Assessment |
|---|---|
| Inside Open WebUI | Not recommended. It introduces arbitrary Python/plugin risk, upgrade fragility, and possible drift from Ageix governance. |
| Beside Open WebUI | Acceptable for a spike or deployment boundary if the adapter is still Ageix-owned, versioned, and governed. |
| Inside Ageix | Preferred long-term. The adapter belongs to `ARCH-AGEIX-HUMANINTERFACE-GOVERNEDINTERACTIONADAPTER` and should call existing governed Ageix capabilities rather than duplicating them. |

Adapter responsibilities:

- Expose narrow, purpose-specific endpoints for Human Interface surfaces.
- Enforce `project_id: "Ageix"` for Ageix-specific endpoints.
- Normalize identity/session/project context before calling Ageix capabilities.
- Capture explicit rationale/justification for future mutation proposals.
- Convert Open WebUI/OpenAPI/MCP metadata into Ageix audit correlation metadata.
- Return summary-first, traceable payloads suitable for UI display.
- Never write directly to Ageix repository, worker state, evidence store, validation state, architecture registry, or approval records.

Adapter non-responsibilities:

- Does not decide approval authority.
- Does not own decision records.
- Does not own approval state.
- Does not execute workers.
- Does not mutate Git.
- Does not replace Ageix MCP/capability authorization.
- Does not depend on the unfinished intent engine.

### 4. Governance constraints

The integration is acceptable only under these invariants:

- No direct UI-to-worker mutation.
- No direct UI-to-repository mutation.
- No separate approval store.
- No Open WebUI authority model for Ageix decisions.
- No Open WebUI plugin or pipeline may execute shell/Git/worker operations for Ageix.
- Open WebUI RBAC gates shell visibility only; Ageix capability governance gates Ageix actions.
- All state-changing requests require explicit human rationale and Ageix-governed capability execution.
- Ageix remains system of record for proposals, evidence, decisions, validation, audit, artifacts, workers, and governance.

### 5. Risks and constraints matrix

| Risk | Severity | Likelihood | Constraint / mitigation |
|---|---:|---:|---|
| Arbitrary Python execution in Open WebUI plugins/functions/pipelines | High | High if plugins are used | Do not install unreviewed community plugins. Avoid plugin-based mutation paths. Prefer Ageix-owned adapter. |
| Open WebUI upgrade fragility for custom UI/pages | Medium | Medium | Avoid core forks for 26.2. Prefer Ageix-hosted/adapter-served surfaces and narrow OpenAPI contracts. |
| Auth/session mismatch between Open WebUI and Ageix | High | Medium | Treat Open WebUI identity as input claims only. Ageix validates/authorizes at adapter boundary. |
| Open WebUI RBAC mistaken for Ageix authority | High | Medium | Document and enforce that RBAC controls shell access only. Ageix governance remains authoritative. |
| UI hard-coupling to chat workflows | Medium | High if Tools are primary | Decision Inbox should be structured/read-only and not depend on model tool calls. |
| Dependency on unfinished intent engine | Medium | Low if avoided | Do not require intent engine. Use explicit deterministic endpoints and registered capability calls. |
| Separate approval state created in Open WebUI | High | Medium | Never store approval state in Open WebUI. Store only display/cache/correlation if absolutely needed and non-authoritative. |
| API keys over-privileged | Medium | Medium | Prefer OIDC/OAuth. If API keys are used, use service accounts and endpoint restrictions. |
| MCP exposed too broadly | High | Medium | Admin-register only, scope access, restrict function list, and rely on Ageix authorization. |
| Shell-only model insufficient for rich UX | Medium | Medium | For 26.2, use read-only structured surface. If rich pages are required, host them in Ageix WebPlatform and link from Open WebUI. |

## Integration recommendation

Open WebUI is suitable as an **initial shell and launcher** for Ageix human-facing workflows, but it should not be treated as the primary host for authoritative Ageix UI state.

Recommended approach:

1. Use Open WebUI as the authenticated human shell.
2. Register a narrow Ageix Human Interface Adapter as an OpenAPI tool server for structured read-only Decision Inbox access.
3. Optionally expose Ageix MCP Streamable HTTP for governed capability discovery and constrained read-only review tools.
4. Keep future approval/manual-trigger mutations inside Ageix governed capabilities, with explicit rationale capture and audit.
5. Avoid Open WebUI Functions/Pipelines for production mutation paths due to arbitrary Python execution and upgrade fragility.
6. Host any non-chat structured pages in Ageix WebPlatform or the Ageix-owned adapter, not inside Open WebUI core.

## Recommendation for Sprint 26.2 Decision Inbox path

Sprint 26.2 can proceed safely only as a **read-only Decision Inbox MVP**.

Recommended 26.2 path:

- Build no production approval actions yet.
- Do not depend on the unfinished intent engine.
- Define deterministic read endpoints for decision/proposal/evidence/validation summary retrieval.
- Return summary-first, traceable records with IDs and governing artifact references.
- Enforce `project_id: "Ageix"` at the adapter boundary.
- Require authenticated identity and Ageix capability authorization even for read surfaces.
- Surface the inbox through Open WebUI as a linked or tool-accessible read surface.
- Do not store decisions, approvals, or workflow state in Open WebUI.

Minimum safe 26.2 contract:

- `GET /human-interface/decision-inbox?project_id=Ageix`
- read-only response
- no mutation fields
- no worker controls
- no Git controls
- no approval/reject buttons
- no local Open WebUI approval state
- explicit access-denied behavior

## Conclusion

Open WebUI can safely participate in the Ageix Human Interface path if it remains shell-only and Ageix owns the adapter, authorization, rationale capture, audit, and state. The safest next step is a read-only Decision Inbox exposed through an Ageix-owned adapter, with Open WebUI used only for access, display, and launch/navigation.

Open WebUI should not host production Ageix approval authority, worker initiation authority, direct repository mutation, or a separate governance store.
