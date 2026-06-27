#!/usr/bin/env bash
# Calls identity.keycloak.client.provision for one MCP client using the
# chair-admin token already present in the environment -- no token paste.
#
# Usage: scripts/Ops/provision_mcp_client.sh <client_id> [session_id]
#   e.g. scripts/Ops/provision_mcp_client.sh claude
set -euo pipefail

MCP_CLIENT_ID="${1:-}"
if [[ -z "$MCP_CLIENT_ID" ]]; then
  echo "Usage: $0 <client_id> [session_id]" >&2
  exit 2
fi

if [[ -z "${AGEIX_CHAIR_ADMIN_TOKEN:-}" ]]; then
  echo "ERROR: AGEIX_CHAIR_ADMIN_TOKEN is not set in the environment." >&2
  exit 2
fi

AGEIX_BASE_URL="${AGEIX_BASE_URL:-http://127.0.0.1:8002}"
PROJECT_ID="${PROJECT_ID:-Ageix}"
SESSION_ID="${2:-kc-provision-${MCP_CLIENT_ID}-$(date +%s)}"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

python3 -c "
import json
print(json.dumps({'context': {'session_id': '${SESSION_ID}', 'project_id': '${PROJECT_ID}'}, 'capability_id': 'identity.keycloak.client.provision', 'arguments': {'mcp_client_id': '${MCP_CLIENT_ID}'}}))
" > "${WORKDIR}/payload.json"

curl -sS -X POST "${AGEIX_BASE_URL}/capabilities/execute" \
  -H "Authorization: Bearer ${AGEIX_CHAIR_ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @"${WORKDIR}/payload.json" | python3 -m json.tool
