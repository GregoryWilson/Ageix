# Sprint 26.0 — Human Interface Architecture Foundation

Project: Ageix  
Status: proposed architecture foundation  
Scope: architecture only  

## Purpose

The Human Interface domain represents governed human interaction with Ageix. It defines how human-facing shells can present Ageix context and collect human intent while preserving Ageix as the system of record.

This artifact does not implement UI functionality.

## Governing architectural intent

This foundation is aligned to the following requested governing artifacts:

- `EVPKG-298023C1EE14`
- `ARCHREVPROP-B2A5E2D22EFD`
- `ADR-0017` / `ADR-1CE374A025B2`
- `PRIN-0007`
- `INTENT-0008`
- `ARCHREV-2F16C935631A`

AgeixAI retrieval confirmed `ADR-1CE374A025B2` as `ADR-0017`, titled `Use Open WebUI as the Initial Ageix Human Interface Shell`. Its governing constraints are preserved here:

- Open WebUI is the initial shell only.
- Ageix-specific governance remains inside Ageix.
- Ageix remains authoritative for proposals, evidence, decisions, validation, artifacts, workers, audit, and governance.
- State-changing UI actions must route through governed Ageix capabilities.
- No direct UI-to-worker mutation path is introduced.

## Architecture node

`ARCH-AGEIX-HUMANINTERFACE` is introduced as a proposed first-level architecture domain under `ARCH-AGEIX-PROJECT`.

Path: `Ageix.HumanInterface`  
Node type: `domain`  
Status: `proposed`  

Description:

> Defines governed human interaction with Ageix for review, approval, feedback, manual workflow initiation, notifications, and future human-facing entry points. This domain does not implement UI functionality and does not own Ageix state.

## Child components

### `ARCH-AGEIX-HUMANINTERFACE-INTERACTIONSHELL`

Defines the presentation-shell boundary for Open WebUI and future human-facing shells. Shells may display Ageix context and collect human input, but they are not authoritative records.

### `ARCH-AGEIX-HUMANINTERFACE-GOVERNEDINTERACTIONADAPTER`

Defines the adapter boundary between a human-facing shell and governed Ageix capabilities. All state-changing actions must route through project-scoped governed capability execution.

### `ARCH-AGEIX-HUMANINTERFACE-DECISIONREVIEW`

Defines human-facing review concepts for proposals, architecture decisions, evidence, validation outcomes, waivers, approvals, and feedback while preserving existing governance paths.

### `ARCH-AGEIX-HUMANINTERFACE-NOTIFICATIONINTAKE`

Defines future notification and lightweight approval-link intake boundaries without introducing mobile implementation or new authority paths.

## Responsibilities

The Human Interface domain is responsible for:

- Presenting governed Ageix context to humans for review and action.
- Collecting human approvals, feedback, decisions, and manual workflow initiation intent.
- Routing state-changing requests through governed project-scoped Ageix capabilities.
- Preserving evidence, validation, proposal, architecture, worker, and audit traceability.
- Defining interface boundaries for Open WebUI and future human-facing shells without implementing them.

## Boundaries

In scope:

- Architecture domain definition.
- Architecture relationships.
- Governed human interaction responsibilities.
- Open WebUI shell boundary.
- No direct UI-to-worker mutation rule.

Out of scope:

- Open WebUI integration implementation.
- Chat feature implementation.
- Mobile implementation.
- New authority paths.
- Governance policy changes.
- Direct worker mutation from UI.

## Architecture relationships

| Source | Relationship | Target | Meaning |
|---|---|---|---|
| `ARCH-AGEIX-HUMANINTERFACE` | `child_of` | `ARCH-AGEIX-PROJECT` | Human Interface is a first-level Ageix architecture domain. |
| `ARCH-AGEIX-HUMANINTERFACE` | `uses_governed_capabilities_from` | `ARCH-AGEIX-MCPPLATFORM` | Human-facing actions enter Ageix through governed capability surfaces. |
| `ARCH-AGEIX-HUMANINTERFACE` | `preserves_governance_of` | `ARCH-AGEIX-GOVERNANCEPLATFORM` | Review, approval, waiver, and feedback flows preserve existing governance semantics. |
| `ARCH-AGEIX-HUMANINTERFACE` | `uses_identity_and_session_context_from` | `ARCH-AGEIX-SESSIONPLATFORM` | Human interaction must remain project-scoped and session-aware. |
| `ARCH-AGEIX-HUMANINTERFACE` | `respects_trust_boundaries_from` | `ARCH-AGEIX-SECURITYPLATFORM` | Interfaces must not bypass admission, identity, authorization, or trust-boundary checks. |
| `ARCH-AGEIX-HUMANINTERFACE-INTERACTIONSHELL` | `shell_only_boundary_for` | `ARCH-AGEIX-WEBPLATFORM` | Open WebUI and future web shells are presentation/input surfaces only. |

## Non-bypass rules

- Human-facing shells do not directly mutate DevJobs, workers, architecture, validation, evidence, or governance state.
- Human Interface does not introduce a worker-control path.
- Human Interface does not create a parallel approval store.
- Human Interface does not grant authority based on UI presence.
- Human Interface does not replace existing capability authorization.

## Validation summary

Repository inspection confirmed the existing architecture registry at `.ageix/architecture/index.json`, including `ARCH-AGEIX-PROJECT` and the current top-level platform domains. Repository inspection also confirmed existing governed conversation capability routing in `services/capabilities/conversation_capabilities.py`, which supports the broader architecture pattern that external/human-facing interactions route through governed capability handlers rather than direct service mutation.

No executable UI code, Open WebUI integration, chat implementation, mobile implementation, governance policy change, or worker-control behavior is introduced by this sprint artifact.
