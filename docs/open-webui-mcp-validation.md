# Open WebUI MCP Validation Guide

Sprint: 26.6 — Open WebUI MCP Validation Wiring

Purpose: validate that Open WebUI can act as a replaceable cockpit for Ageix-governed shared conversations through the existing MCP interface.

## Authority boundary

Open WebUI is a client only.

Ageix remains authoritative for:

- identity
- governance
- explicit project context
- conversation state
- participant registration
- immutable turns
- HANDOFF_PACKAGE artifacts
- audit

Do not configure Open WebUI as a source of truth for Ageix conversation history or participant state. Do not duplicate conversation state into Open WebUI memory, knowledge bases, RAG stores, or workflow state for this validation.

## Required MCP server configuration

Configure Open WebUI to connect to the existing Ageix MCP endpoint exposed by the Ageix service.

Use the operator-selected URL for the running environment, for example:

```text
https://ageix.wilsongpt.com/mcp
```

or, for LAN-only validation:

```text
http://<ageix-vm-host-or-ip>:8000/mcp
```

Authentication must use the existing Ageix-authenticated MCP context. Identity must be resolved by Ageix from authenticated request context, not from Open WebUI-authored participant fields.

Every governed capability call that requires project scope must include:

```json
{
  "project_id": "Ageix"
}
```

## Required capability surface

Open WebUI must discover and exercise the existing Ageix conversation capabilities:

- `ageix.conversation.open`
- `ageix.conversation.turn.append`
- `ageix.conversation.turn.list`
- `ageix.conversation.get`
- `ageix.conversation.participant.list`
- `ageix.conversation.handoff.create`
- `ageix.conversation.handoff.get`

Do not replace or wrap these contracts for Sprint 26.6 validation.

## Manual validation sequence

1. Connect Open WebUI to the Ageix MCP server.
2. Discover tools and confirm the conversation capabilities are present.
3. Open a governed conversation with Open WebUI represented as a participant.
4. Append a turn using `ageix.conversation.turn.append`.
5. Retrieve the turn history using `ageix.conversation.turn.list`.
6. Retrieve the conversation using `ageix.conversation.get`.
7. Retrieve participants using `ageix.conversation.participant.list`.
8. Create a handoff artifact using `ageix.conversation.handoff.create`.
9. Retrieve that artifact using `ageix.conversation.handoff.get`.
10. Restart Open WebUI.
11. Retrieve the same conversation and handoff package again through Ageix MCP.

Passing result: conversation and handoff state remain available after the Open WebUI restart because Ageix, not Open WebUI, owns the authoritative state.

## Smoke validation performed by DevWorker

The following governed MCP capability flow was executed against the live Ageix project context:

- Listed capabilities and confirmed the required conversation capability surface is exposed.
- Opened governed conversation `CONV-77FF150A30D5`.
- Appended immutable turn `TURN-FC9BDD38CCE1`.
- Retrieved turn history using `conversation.turn.list`.
- Retrieved conversation state using `conversation.get`.
- Created HANDOFF_PACKAGE `HANDOFF-C014657CDB2C`.
- Retrieved HANDOFF_PACKAGE `HANDOFF-C014657CDB2C`.

Observed boundary behavior:

- The conversation was scoped to `project_id="Ageix"`.
- The conversation and handoff were stored and retrieved through Ageix-governed capabilities.
- Open WebUI was treated only as a participant/client identity in the validation metadata.
- No OpenAI-compatible gateway, provider routing, model routing, RAG, memory, or workflow integration was introduced.

## Acceptance checklist

- [ ] Open WebUI can connect to the Ageix MCP endpoint.
- [ ] Open WebUI can discover the conversation capabilities.
- [ ] Open WebUI can open a governed conversation.
- [ ] Open WebUI can append immutable turns.
- [ ] Open WebUI can retrieve turn history.
- [ ] Open WebUI can retrieve registered participants.
- [ ] Open WebUI can create HANDOFF_PACKAGE artifacts.
- [ ] Open WebUI can retrieve HANDOFF_PACKAGE artifacts.
- [ ] Conversation history survives Open WebUI restart.
- [ ] Identity remains resolved by authenticated Ageix context.
- [ ] Project context remains explicit as `project_id="Ageix"`.
- [ ] No governance bypass is introduced.

## Non-goals

This validation guide intentionally does not introduce:

- OpenAI-compatible Ageix gateway
- provider routing
- model routing
- RAG integration
- Open WebUI memory integration
- Open WebUI knowledge base integration
- Open WebUI workflow engine integration
- Open WebUI authority model
- Intent subsystem work
- ADR-0020 concepts
