# Sprint 26.6 Human Consultation Framework Validation

## Scope

Sprint 26.6 implements a generalized Human Consultation Framework with constrained decision choices.

Authoritative architecture context:

- AgeixAI Project: `Ageix`
- Architecture Finding: `ARCHFIND-A8A100EB0C79`
- Architecture Node: `ARCH-AGEIX-GOVERNANCEPLATFORM-CONSULTATIONFRAMEWORK`

Core boundary preserved:

- The multiple-choice framework is the protocol.
- Open WebUI remains only the shell.
- Ageix owns consultation state, valid choice generation, choice validation, response execution, routing, audit path, and lifecycle mutation.

## Files changed

- `models/human_consultation.py`
- `services/human_consultation_service.py`
- `services/capabilities/human_consultation_response_capabilities.py`
- `services/human_interface_decision_inbox_service.py`
- `tests/test_human_consultation_request_model.py`
- `tests/test_human_consultation_response_capability.py`
- `tests/test_human_consultation_decision_inbox.py`
- `.ageix/architecture/validation/sprint_26_6_human_consultation_framework_validation.md`

## Capability added

### `human.consultation.respond`

Registered in `services/capabilities/human_consultation_response_capabilities.py` and implemented by `HumanConsultationService`.

Behavior:

- Validates `project_id` against `Ageix`.
- Requires `consultation_id`.
- Rejects malformed consultation IDs before consultation filesystem lookup.
- Rejects unknown consultations.
- Rejects invalid choices.
- Enforces per-choice `requires_rationale`.
- Enforces per-choice `requires_text` for `other` and future text-bearing choices.
- Rejects non-Chair roles for state-changing responses.
- For approval consultations targeting proposals, routes to `proposal.approval.execute`.
- For approval consultations targeting ADRs, routes to `architecture.adr.approval.execute`.
- Does not implement proposal or ADR approval lifecycle semantics directly.

## Model/schema added

### `HumanConsultationRequest`

Canonical consultation ID format: `^HCONS-[A-F0-9]{12}$`

Fields implemented:

- `consultation_id`
- `project_id`
- `consultation_type`
- `question`
- `summary`
- `context`
- `choices`
- `status`
- `system_of_record`
- response metadata fields for selected choice, rationale, freeform text, and routed result

Supported consultation types:

- `approval`
- `missing_evidence`
- `missing_context`
- `ambiguity`
- `prioritization`
- `risk_acceptance`
- `architecture_decision`
- `other`

Initial choice helpers implemented:

- Approval choices: `approve`, `reject`, `add_comment`, `other`
- Missing evidence choices: representable without execution logic
- Missing context choices: representable without execution logic

## Consultation ID validation hardening

Security review finding addressed:

- `HumanConsultationRequest.consultation_id` now enforces the canonical Ageix consultation ID format: `^HCONS-[A-F0-9]{12}$`.
- A shared `is_valid_human_consultation_id()` helper backs service-side validation.
- `HumanConsultationService.respond()` rejects malformed IDs with `invalid_consultation_id` during common argument validation.
- `HumanConsultationService.create_request()` rejects invalid request IDs before writes.
- `HumanConsultationService.get_request()` rejects invalid request IDs before filesystem resolution or reads.
- `HumanConsultationService._write()` rejects invalid request IDs before directory creation or file writes.
- `HumanConsultationService._path()` performs a final guard before resolving the consultation file location.

Filesystem boundary evidence:

- Invalid IDs return `invalid_consultation_id` before request lookup.
- Invalid IDs do not create consultation directories.
- Invalid IDs do not write consultation files.
- Invalid IDs do not mutate existing consultation lifecycle state.
- Path-manipulation inputs and lowercase hex IDs are rejected before filesystem resolution.

New test evidence:

- `tests/test_human_consultation_request_model.py` validates model-level rejection of malformed consultation IDs, lowercase hex IDs, and path-manipulation IDs.
- `tests/test_human_consultation_response_capability.py` validates service/capability rejection of malformed consultation IDs, lowercase hex IDs, and path-manipulation IDs.
- Service boundary tests monkeypatch request lookup and path resolution to fail if reached, verifying invalid IDs are rejected before filesystem lookup or path resolution.

## Decision Inbox read-only evidence

`HumanInterfaceDecisionInboxService` remains a read-only projection service.

Evidence:

- `get_decision_inbox()` composes records and returns a projection only.
- Pending proposal and ADR records include Ageix-generated `consultation_metadata` and constrained choices.
- Pending persisted consultation records are surfaced as read-only inbox records.
- The service does not call `CapabilityExecutionService`.
- The service does not call Git.
- The service does not write proposal, ADR, evidence, validation, architecture, decision trace, or consultation state during inbox reads.
- `tests/test_human_consultation_decision_inbox.py` snapshots files before and after inbox read and asserts no changes.
- Existing `tests/test_human_interface_decision_inbox.py` remains part of the focused validation command.

## Open WebUI shell-only evidence

No Open WebUI state or lifecycle ownership was added.

Evidence:

- No `open_webui/*` files were changed.
- `human_interface_adapter.py` was not changed.
- Consultation state is stored by Ageix under the human consultations store through `HumanConsultationService`.
- Response execution is exposed through governed Ageix capability infrastructure.
- Approval-style execution delegates to Sprint 26.5 target-specific capabilities.

## Boundary evidence

- Human Consultation does not mutate proposal or ADR state directly for approval choices.
- Approval routing uses `CapabilityExecutionService` and target capabilities:
  - `proposal.approval.execute`
  - `architecture.adr.approval.execute`
- Human Consultation records its own `answered` lifecycle only after routed approval succeeds.
- Returned payloads include:
  - `mutation_performed_by_human_interface: false`
  - `approval_semantics_implemented_by_human_consultation: false`
  - `open_webui_state_owner: false`

## Tests run

Expected focused validation command:

```bash
pytest \
  tests/test_human_consultation_request_model.py \
  tests/test_human_consultation_response_capability.py \
  tests/test_human_consultation_decision_inbox.py \
  tests/test_human_interface_decision_inbox.py \
  tests/test_human_interface_governed_approval_routing.py
```

Result: NOT RUN by this DevWorker session.

Reason: this implementation was delivered through the GitHub connector without an executable local checkout of the PR branch available to the session. An attempted AgeixAI validation profile query for project `Ageix` was blocked by platform safety checks, so no branch-selectable validation run was available in this session.

## Pass/fail result

- Static implementation review: PASS
- Focused test execution: NOT RUN
- Broader regression: NOT RUN

## Known limitations

- Missing evidence and missing context consultations are representable and answerable, but no downstream execution logic is implemented for those consultation types yet.
- `human.consultation.respond` is registered as a governed capability and can be invoked through the generic capability execution path; no dedicated MCP tool definition was added in this sprint.
- Consultation request creation is implemented as an Ageix service API for internal producers; no external request-creation capability was added in this minimal sprint.
- Validation should be run on the PR branch before merge.
