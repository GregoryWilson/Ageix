# Sprint 26.4 — Governed Approval Execution Validation

Date: 2026-07-01
Project: Ageix
Branch: sprint-26-4-governed-approval-execution

## Scope

Sprint 26.4 introduces the first executable Human Interface mutation path for governed decision actions.

Supported actions:

- approve
- reject
- defer
- request_changes
- add_comment

Supported target types:

- proposal / pending_proposal
- adr / architecture_decision / architecture_decision_record / pending_architecture_decision

## Governance Verification Summary

The implementation preserves the Human Interface Adapter as a translation layer only.

The adapter:

- requires an authenticated boundary before action execution
- requires explicit `project_id`
- requires `target_record_id`
- requires `target_record_type`
- requires a supported action
- requires rationale
- builds an authenticated identity context
- delegates execution to `CapabilityExecutionService`
- does not write repository files directly
- does not invoke Git
- does not invoke workers
- does not create Open WebUI approval state

Governed execution is routed through:

1. `human_interface_adapter.py`
2. `HumanInterfaceGovernedApprovalService`
3. `CapabilityExecutionService`
4. `AgentAuthorizationService`
5. registered capability `human_interface.approval.execute`
6. existing Ageix system-of-record services:
   - `ProposalService`
   - `ArchitectureDecisionRecordService`
   - `DecisionTraceService`
   - `CapabilityAuditService`

## Existing Governed Infrastructure Reused

Reused components:

- `CapabilityExecutionService` for capability lookup, authorization, execution, workflow event recording, and audit recording
- `AgentAuthorizationService` for capability authorization and role-policy enforcement
- `ProposalService` for governed proposal status updates and rationale/comment metadata
- `ArchitectureDecisionRecordService` for ADR acceptance after proposal approval
- `DecisionTraceService` for append-only decision trace generation
- `CapabilityAuditService` for capability audit linkage

The sprint adds an adapter-facing governed capability registration, not a duplicate approval system.

## Mutation Boundary

Repository/system-of-record updates occur inside Ageix governed services invoked by the governed capability handler.

The Human Interface Adapter does not directly mutate:

- proposals
- ADRs
- decision traces
- evidence packages
- validation artifacts
- repository files
- Git state
- worker state
- Open WebUI state

## Failure Behavior

Implemented structured failure responses for:

- missing authorization
- missing project_id
- invalid project
- missing target_record_id
- missing target_record_type
- missing action
- unsupported action
- missing rationale
- invalid target
- capability authorization denial
- capability unavailable
- governance rejection

Validation failures are rejected before capability execution and before target mutation.

## Validation Evidence

Tests added in `tests/test_human_interface_governed_approval.py` cover:

- successful approval
- successful rejection
- successful defer
- successful request changes
- successful comment/rationale submission
- missing rationale
- missing authorization
- invalid project
- unsupported action
- invalid record
- capability denial
- audit creation
- decision trace creation
- Decision Inbox regression

Decision Detail regression was not added because the currently inspected `main` branch did not expose a Decision Detail service or route under the expected Human Interface files.

## Tests

Recommended command:

```bash
pytest tests/test_human_interface_decision_inbox.py tests/test_human_interface_governed_approval.py
```

Tool-context status: tests were added for the requested paths, but were not executed in this ChatGPT GitHub connector session because the active tool context provided repository file operations but not a checked-out runtime test environment.

## Known Risks

- The implementation relies on the existing `CapabilityExecutionService` authorization/audit path and the existing proposal/ADR services as the governance authority.
- Full multi-file transactional rollback is not introduced in this sprint. Request validation failures occur before mutation. Runtime exceptions from reused system-of-record services are surfaced as governance failures.
- Validation evidence generation is represented by decision trace and audit linkage for approval actions. No new validation run is started because the sprint forbids worker execution and direct repository mutation from the adapter.

## Conclusion

Sprint 26.4 preserves Ageix as the system of record and Open WebUI as a shell. The Human Interface Adapter translates authenticated user action requests into a governed Ageix capability invocation. Capability authorization, project authorization, rationale enforcement, audit linkage, and decision trace generation remain inside Ageix governed infrastructure.
