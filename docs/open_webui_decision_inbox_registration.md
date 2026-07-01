# Open WebUI Decision Inbox Registration

Project: Ageix  
Sprint: 26.2.5  
Surface: read-only Human Interface Decision Inbox  
Registration artifact: `open_webui/decision_inbox_openapi.json`

## Purpose

This document describes the narrow Open WebUI registration path for the Ageix Decision Inbox MVP.

Open WebUI remains an interaction shell only. Ageix remains the system of record, authorization authority, project-scope authority, and governance authority.

## Selected integration path

Use an OpenAPI tool-server registration pointed at the Ageix-owned Human Interface Adapter.

Preferred live registration URL when the adapter is running:

```text
https://ageix.wilsongpt.com/openapi.json
```

Local/dev registration URL when running the adapter directly:

```text
http://localhost:8000/openapi.json
```

Static registration artifact for review or manual import:

```text
open_webui/decision_inbox_openapi.json
```

MCP Streamable HTTP is not required for this sprint. Open WebUI plugin code, pipeline code, and arbitrary Python execution are not required for production use.

## Adapter endpoint

```http
GET /human-interface/decision-inbox?project_id=Ageix
Authorization: Bearer <Ageix-authorized-token>
```

The endpoint is exposed by the Ageix Human Interface Adapter FastAPI app. The OpenAPI-compatible app surface is `human_interface_gateway.app`, which includes the `human_interface_adapter` router.

## Open WebUI setup

1. Start the Ageix Human Interface Adapter.
2. Confirm the Ageix adapter OpenAPI document is reachable from the Open WebUI host:

   ```bash
   curl -sS http://localhost:8000/openapi.json | jq '.paths["/human-interface/decision-inbox"].get.operationId'
   ```

3. In Open WebUI, register an OpenAPI tool server using the adapter OpenAPI URL:

   ```text
   http://localhost:8000/openapi.json
   ```

   Use the production gateway URL instead when Open WebUI is calling the deployed Ageix gateway.

4. Configure bearer-token authorization for the registered tool server. The token must be accepted by Ageix. Open WebUI workspace, chat, model, or group context is not Ageix authorization.
5. Use the registered operation:

   ```text
   get_ageix_decision_inbox
   ```

6. Supply the required query parameter exactly:

   ```text
   project_id=Ageix
   ```

## Expected smoke checks

Authorized read:

```bash
curl -sS \
  -H "Authorization: Bearer $AGEIX_TOKEN" \
  "http://localhost:8000/human-interface/decision-inbox?project_id=Ageix" \
  | jq '.summary.mode, .read_only, .summary.mutation_controls_exposed'
```

Expected values:

```text
"read_only"
true
false
```

Missing project context denied:

```bash
curl -i -sS \
  -H "Authorization: Bearer $AGEIX_TOKEN" \
  "http://localhost:8000/human-interface/decision-inbox"
```

Expected result: HTTP 403 with `error: project_id_required`.

Incorrect project context denied:

```bash
curl -i -sS \
  -H "Authorization: Bearer $AGEIX_TOKEN" \
  "http://localhost:8000/human-interface/decision-inbox?project_id=Other"
```

Expected result: HTTP 403 with `error: project_scope_denied`.

Missing authorization denied:

```bash
curl -i -sS \
  "http://localhost:8000/human-interface/decision-inbox?project_id=Ageix"
```

Expected result: HTTP 403 with `error: authorization_required`.

## Governance constraints preserved

This registration path exposes only a GET operation. It does not expose approval, rejection, deferral, request-changes, rationale/comment mutation, worker execution, notification behavior, repository mutation, Open WebUI approval state, Open WebUI plugin code, Open WebUI pipeline code, or dependency on the unfinished intent engine.
