# Sprint 26.3 Decision Detail + Governed Approval Action Design Validation

Project: Ageix  
Sprint: 26.3  
Title: Decision Detail + Governed Approval Action Design  
Status: implementation validation prepared

## Scope validated

Sprint 26.3 extends the Ageix Human Interface Adapter with a read-only Decision Detail surface and defines non-executable governed action contract metadata for future Chair approval workflows.

Added endpoint:

```http
GET /human-interface/decision-detail/{decision_id}?project_id=Ageix
```

Existing endpoint preserved:

```http
GET /human-interface/decision-inbox?project_id=Ageix
```

## Governance assertions

- Ageix remains the system of record.
- Open WebUI remains shell only.
- Decision Detail requires explicit `project_id=Ageix`.
- Missing authorization is denied before service execution.
- Missing project context is denied.
- Incorrect project context is denied.
- Decision Detail is read-only.
- No approval, rejection, deferral, request-change, or comment/rationale mutation is executed.
- No repository mutation path is added.
- No worker trigger path is added.
- No validation job trigger path is added.
- No Open WebUI-owned approval state is introduced.
- Governed action contracts are metadata only in Sprint 26.3.

## Decision Detail response shape

The detail response is summary-first and includes, where available:

- `decision_id`
- `record_id`
- `record_type`
- `status`
- `title`
- `objective`
- `summary_text`
- governing artifact references
- governing architecture files
- evidence links
- validation links
- decision trace links
- available next governed action labels
- rationale requirement metadata
- authority requirement metadata
- disabled governed action contracts
- source record and source detail context

## Governed action contracts defined

Sprint 26.3 defines these future action contracts as non-executable metadata:

- `approve`
- `reject`
- `defer`
- `request_changes`
- `add_comment/rationale`

Each contract requires:

- `project_id: "Ageix"`
- target record ID
- target record type
- explicit rationale
- authenticated identity
- capability authorization
- decision trace update
- audit linkage
- validation evidence where applicable

## Validation coverage added

New or extended tests cover:

- missing authorization denied for Decision Detail
- missing project denied for Decision Detail
- incorrect project denied for Decision Detail
- valid detail read from existing Ageix stores
- summary-first, traceable detail response shape
- disabled governed action contracts
- no executable mutation controls exposed as URLs or executable transport
- read-only detail operation does not mutate repository files
- OpenAPI registration exposes Decision Detail as GET-only
- OpenAPI action contract schema remains non-executable
- Decision Inbox regression behavior remains covered

## Validation commands

Required command:

```bash
pytest tests/test_human_interface_decision_inbox.py tests/test_open_webui_decision_inbox_registration.py
```

Sprint 26.3-specific tests are included in the same files above.

## Validation note

The ChatGPT execution environment could not clone GitHub directly due DNS resolution failure for `github.com`, so local pytest execution was not available from this environment. Static review was performed through the GitHub connector against branch `sprint-26-3-decision-detail-approval-design`.

## Regression risk

Low to moderate.

The implementation reuses the existing Human Interface Decision Inbox service and adapter authorization pattern. Risk is concentrated in response-shape expectations and OpenAPI registration compatibility. No mutation path was added.

## 26.4 readiness assessment

Sprint 26.4 can proceed to governed approval execution design only after Sprint 26.3 tests pass in the repository environment and the existing governed capability path for approval execution is identified, tested, and auditable. Sprint 26.3 intentionally does not prove executable approval mutations.
