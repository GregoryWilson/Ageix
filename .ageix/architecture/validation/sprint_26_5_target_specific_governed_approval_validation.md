# Sprint 26.5 Target-Specific Governed Approval Validation

## Scope

Sprint 26.5 implements target-specific governed approval execution for:

- `proposal.approval.execute`
- `architecture.adr.approval.execute`

Governing architecture context:

- Proposal approval architecture revision: `ARCHREVPROP-70149C8B2E45`
  - Linked proposal: `PROP-F0AC13794F49`
- ADR approval architecture revision: `ARCHREVPROP-29197941764A`
  - Linked proposal: `PROP-C91F731F7542`
- Human Interface routing-boundary architecture revision: `ARCHREVPROP-408E502EB66A`
  - Linked proposal: `PROP-4492C7EC5C6D`
- ADR proposal: `ADR-C6D906554D3B` / `ADR-0018`
  - Linked proposal: `PROP-131567CC9AD2`

## Files changed

- `services/proposal_approval_service.py`
- `services/architecture_adr_approval_service.py`
- `services/capabilities/proposal_approval_capabilities.py`
- `services/capabilities/architecture_adr_approval_capabilities.py`
- `services/capabilities/human_interface_approval_capabilities.py`
- `tests/test_proposal_approval_capability.py`
- `tests/test_architecture_adr_approval_capability.py`
- `tests/test_human_interface_governed_approval_routing.py`
- `.ageix/architecture/validation/sprint_26_5_target_specific_governed_approval_validation.md`

## Target-specific capabilities added

### `proposal.approval.execute`

Registered in `services/capabilities/proposal_approval_capabilities.py` and implemented by `ProposalApprovalService`.

Behavior:

- `approve` transitions mutable Proposal System statuses to `approved`.
- `reject` transitions mutable Proposal System statuses to `denied`.
- `add_comment` appends a governance-visible `governance_comments` metadata entry without changing proposal lifecycle status.
- `defer` returns `unsupported_action_for_target` because the current `ProposalStatus` enum has no deferred lifecycle status.
- `request_changes` returns `unsupported_action_for_target` because the current `ProposalStatus` enum has no changes-requested lifecycle status.

### `architecture.adr.approval.execute`

Registered in `services/capabilities/architecture_adr_approval_capabilities.py` and implemented by `ArchitectureAdrApprovalService`.

Behavior:

- `approve` accepts a proposed/draft ADR through the existing `ArchitectureDecisionRecordService.accept_approved_adr` governance path, requiring the linked ADR proposal to already be approved.
- `reject` marks mutable ADR statuses as `rejected`.
- `add_comment` appends a governance-visible `governance_comments` metadata entry without changing ADR lifecycle status.
- `defer` returns `unsupported_action_for_target` because the current `ArchitectureDecisionRecordStatus` enum has no deferred lifecycle status.
- `request_changes` returns `unsupported_action_for_target` because the current `ArchitectureDecisionRecordStatus` enum has no changes-requested lifecycle status.

## Human Interface boundary evidence

- `services/human_interface_governed_approval_service.py` was not modified.
- `human_interface_adapter.py` was not modified.
- `open_webui/decision_inbox_openapi.json` was not modified.
- `services/capabilities/human_interface_approval_capabilities.py` remains a routing capability. It validates request shape, selects the target capability route, and delegates to `CapabilityExecutionService`.
- Human Interface routing responses preserve `mutation_performed_by_human_interface: false` and `approval_semantics_implemented_by_human_interface: false`.

## Decision Inbox read-only evidence

- `open_webui/decision_inbox_openapi.json` was not changed.
- `tests/test_human_interface_decision_inbox.py` was not changed.
- Decision Inbox remains GET/read-only and continues to expose no mutation controls.

## Validation commands

Recommended focused validation command for this sprint:

```bash
pytest \
  tests/test_human_interface_decision_inbox.py \
  tests/test_human_interface_governed_approval_routing.py \
  tests/test_proposal_approval_capability.py \
  tests/test_architecture_adr_approval_capability.py
```

Governed AgeixAI validation run executed under project `Ageix`:

```bash
python -m pytest tests -q
```

Validation run:

- Run ID: `VALRUN-6A5D02427160`
- Evidence package: `EVPKG-09ECAF64956C`
- Artifact: `ART-7F84CD6091E9`
- Result: PASS
- Return code: 0
- Summary: `804 passed, 1 warning in 130.10s (0:02:10)`

## Known limitations

- `defer` is intentionally unsupported for both target families until the current lifecycle models add a deferred state.
- `request_changes` is intentionally unsupported for both target families until the current lifecycle models add a changes-requested state.
- ADR approval does not mutate proposal state. It requires the linked ADR proposal to already be approved, consistent with existing `accept_approved_adr` governance.
- Proposal approval does not mutate ADR state.
