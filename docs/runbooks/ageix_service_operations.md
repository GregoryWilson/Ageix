# Ageix Service Operations Runbook

This runbook records the minimum operational checks needed after architecture, MCP, or authentication changes.

## Start

From the repository root:

```bash
PYTHONPATH=. ./venv/bin/uvicorn web.app:create_app --factory --host 127.0.0.1 --port 8000
```

## Stop

If Uvicorn is running in the foreground, use `Ctrl+C`. If it is detached, identify and stop it:

```bash
ps aux | grep -i uvicorn | grep -v grep
kill <pid>
```

## Restart

Restart after code, auth config, MCP registry, or architecture capability changes:

```bash
kill <pid>
PYTHONPATH=. ./venv/bin/uvicorn web.app:create_app --factory --host 127.0.0.1 --port 8000
```

A future sprint should replace this manual process with a managed systemd service.

## Auth Refresh Validation

After restart, validate that authentication is enabled and the expected client is resolved:

```bash
curl -i https://ageix.wilsongpt.com/health \
  -H "Authorization: Bearer $AGEIX_DEV_AUTH_TOKEN"
```

Expected metadata includes `auth_enabled: true` and the authenticated client ID.

## MCP publication validation

After MCP capability changes, verify published tool discovery:

```bash
curl -H "Authorization: Bearer $AGEIX_DEV_AUTH_TOKEN" \
  https://ageix.wilsongpt.com/mcp/tools
```

Confirm new tools appear in discovery, `capabilities.list`, and `capabilities.execute` before treating publication as complete.

## Architecture Platform Checks

For architecture hardening releases, validate:

```bash
PYTHONPATH=. python scripts/Smoke/smoke_18_4_architecture_platform_hardening.py
PYTHONPATH=. python -m pytest tests/test_sprint_18_4_architecture_platform_hardening.py -q
```

The smoke test should confirm official project seeding, baseline validation, MCP architecture review submission, challenge capture, and governed revision proposal handoff.
