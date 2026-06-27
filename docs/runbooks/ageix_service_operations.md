# Ageix Service Operations Runbook

This runbook records the minimum operational checks needed after architecture, MCP, or authentication changes.

## Start / Stop / Restart

Use `scripts/Ops/restart_ageix.sh`, which finds the daemon by process pattern, stops
it cleanly (SIGTERM, falling back to SIGKILL), starts it detached in the background,
and polls `/health` until it responds:

```bash
scripts/Ops/restart_ageix.sh start    # start if not already running
scripts/Ops/restart_ageix.sh stop     # stop if running
scripts/Ops/restart_ageix.sh          # restart (default action)
```

Defaults to `127.0.0.1:8002` (matching the `AGEIX_BASE_URL` default used by every
other `scripts/Ops/*.sh` script), logs to `/tmp/ageix_uvicorn.log`, and records the
PID in `/tmp/ageix_uvicorn.pid`. Override via `AGEIX_HOST`, `AGEIX_PORT`, `VENV_PATH`,
`LOG_FILE`, `PID_FILE`, or `HEALTH_TIMEOUT` env vars -- see the script header for
details.

If you need to do it by hand instead:

```bash
ps aux | grep -i uvicorn | grep -v grep
kill <pid>
PYTHONPATH=. ./venv/bin/uvicorn web.app:create_app --factory --host 127.0.0.1 --port 8002
```

A future sprint should replace this with a managed systemd service.

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
