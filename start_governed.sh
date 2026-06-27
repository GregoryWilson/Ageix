#!/bin/bash
# Runs the governed service boundary (web/app.py) alongside the legacy
# app.py started by start.sh. This is what /capabilities/execute, the
# OAuth .well-known discovery routes, and the ageix_mcp transport live on --
# none of that exists on the app.py:8000 process.
#
# Required for Keycloak provisioning (services/keycloak_admin_service.py):
#   export KEYCLOAK_ADMIN_USERNAME=...
#   export KEYCLOAK_ADMIN_PASSWORD=...
# Optional overrides (defaults match compose.yaml): KEYCLOAK_BASE_URL,
# KEYCLOAK_REALM, KEYCLOAK_ADMIN_REALM, KEYCLOAK_ADMIN_CLIENT_ID.

exec uvicorn web.app:app --reload --port 8002
