# Sprint 26.4 — Governed Approval Execution Validation

Date: 2026-07-01
Project: Ageix
Branch: sprint-26-4-governed-approval-execution

## Revision Status

This validation artifact reflects the Sprint 26.4 correction that `human_interface.approval.execute` must be routing/translation only.

The previous implementation incorrectly placed target-specific approval semantics inside the Human Interface capability. That behavior was removed.

## Corrected Scope

Sprint 26.4 now provides:

- Human Interface action endpoint
- request shape validation
- explicit `project_id=Ageix` enforcement
- authenticated identity requirement
- rationale requirement
- supported action validation
- target type routing
- structured `capability_unavailable` response when the target-specific governed capability does not exist

Sprint 26.4 does not implement target-specific approval semantics.

## Supported Human Interface Actions

- approve
- reject
- defer
- request_changes
- add_comment

## Target Routing

Current routing table:

- `proposal` / `pending_proposal` -> `proposal.approval.execute`
- `adr` / `architecture_decision` / `architecture_decision_record` / `pending_architecture_decision` -> `architecture.adr.approval.execute`

Repository/capability inspection did not identify existing target-specific governed approval capabilities for those routes in the current branch context.

Therefore valid requests currently return:

```json
{
  "success": false,
  "error": "capability_unavailable"
}
```

## Governance Verification Summary

The Human Interface Adapter and Human Interface approval capability do not:

- map approval actions to proposal statuses
- mutate proposal status
- mutate proposal metadata or conditions
- accept ADRs
- create decision traces as the primary governance path
- create Open WebUI approval state
- invoke Git
- invoke workers
- implement target-specific approval semantics

The Human Interface layer may only validate and route requests to existing target-specific governed capabilities.

## Existing Infrastructure Reused

Reused components:

- `CapabilityExecutionService` for capability authorization, execution boundary, workflow event handling, and audit recording
- `AgentAuthorizationService` for role/capability authorization
- `CapabilityRegistryService` for target-specific capability lookup

Target-specific system-of-record services are intentionally not invoked by Human Interface routing when the target-specific governed approval capability is absent.

## Mutation Boundary

No target state mutation occurs in Sprint 26.4 when target-specific approval capabilities are unavailable.

Expected target state remains unchanged for valid Human Interface action requests until a proper target-specific governed approval capability exists.

Capability audit records may still be written by the existing capability execution infrastructure to document the failed routed attempt.

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
- invalid target type
- capability authorization denial
- missing target-specific governed approval capability

## Validation Evidence

The intended revised tests should verify:

- valid approve returns `capability_unavailable` and does not mutate target state
- valid reject returns `capability_unavailable` and does not mutate target state
- valid defer returns `capability_unavailable` and does not mutate target state
- valid request_changes returns `capability_unavailable` and does not mutate target state
- valid add_comment returns `capability_unavailable` and does not mutate target state
- missing rationale is rejected before routing
- missing authorization is rejected before routing
- invalid project is rejected before routing
- unsupported action is rejected before routing
- non-Chair role denial occurs before routing
- no decision trace is created by Human Interface routing
- Decision Inbox remains read-only

## Tool Limitation During Revision

The GitHub connector accepted the routing-only implementation update but repeatedly blocked updates and deletion attempts for the existing test file `tests/test_human_interface_governed_approval.py` after the revision request.

As a result, that test file may still contain stale expectations from the superseded implementation and must be corrected locally before merge.

Do not merge until the stale tests are revised or removed and the focused routing-only test suite passes.

## Recommended Test Command

```bash
pytest tests/test_human_interface_decision_inbox.py tests/test_human_interface_governed_approval.py
```

## Known Gap

The required target-specific governed approval capabilities do not appear to exist yet:

- `proposal.approval.execute`
- `architecture.adr.approval.execute`

This is the correct Sprint 26.4 outcome under the revised constraint. A later sprint should implement those capabilities under the proper governance domains, not under Human Interface.

## Conclusion

Sprint 26.4 now preserves Human Interface as a routing and translation layer. The action endpoint can receive and validate governed action requests, but target-specific approval execution remains unavailable until proper governed approval capabilities are implemented outside the Human Interface domain.
