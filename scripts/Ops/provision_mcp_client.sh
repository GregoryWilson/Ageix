#!/usr/bin/env bash
# Calls identity.keycloak.client.provision for one MCP client.
# Generates a fresh admin token on demand from durable credentials stored in
# the environment -- no pre-baked AGEIX_CHAIR_ADMIN_TOKEN needed, so this
# can't go stale the way a manually-exported bearer token can.
#
# Usage: scripts/Ops/provision_mcp_client.sh <client_id> [session_id]
#   e.g. scripts/Ops/provision_mcp_client.sh claude
#
# Durable credentials required in environment (or in a .env file at the
# repo root, which is sourced automatically if present):
#   AGEIX_CHAIR_ADMIN_CLIENT_ID  Keycloak confidential client ID for the
#                                chair-admin service account
#   AGEIX_CHAIR_ADMIN_SECRET     that client's secret
#   AGEIX_KEYCLOAK_URL           e.g. https://auth.wilsongpt.com
#   AGEIX_REALM                  e.g. ageix
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -f "${REPO_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.env"
  set +a
fi

MCP_CLIENT_ID="${1:-}"
if [[ -z "$MCP_CLIENT_ID" ]]; then
  echo "Usage: $0 <client_id> [session_id]" >&2
  exit 2
fi

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib/fetch_chair_admin_token.sh"

AGEIX_BASE_URL="${AGEIX_BASE_URL:-http://127.0.0.1:8002}"
PROJECT_ID="${PROJECT_ID:-Ageix}"
SESSION_ID="${2:-kc-provision-${MCP_CLIENT_ID}-$(date +%s)}"

echo "Fetching admin token from Keycloak..." >&2
fetch_chair_admin_token

echo "Token acquired. Provisioning MCP client '${MCP_CLIENT_ID}'..." >&2

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
