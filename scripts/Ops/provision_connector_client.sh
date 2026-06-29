#!/usr/bin/env bash
# Calls identity.keycloak.connector.provision to create or update a public,
# PKCE-required Keycloak client for a human-delegated OAuth connector (e.g.
# Claude.ai's "Add custom connector" feature) -- mints a fresh chair-admin
# token from Keycloak via the durable client credentials, no token paste.
#
# Usage: scripts/Ops/provision_connector_client.sh <connector_id> <redirect_uri> [<redirect_uri> ...]
#   e.g. scripts/Ops/provision_connector_client.sh claude-ai https://claude.ai/api/mcp/auth_callback
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -f "${REPO_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.env"
  set +a
fi
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib/fetch_chair_admin_token.sh"

CONNECTOR_ID="${1:-}"
if [[ -z "$CONNECTOR_ID" || $# -lt 2 ]]; then
  echo "Usage: $0 <connector_id> <redirect_uri> [<redirect_uri> ...]" >&2
  exit 2
fi
shift
REDIRECT_URIS=("$@")

echo "Fetching admin token from Keycloak..." >&2
fetch_chair_admin_token

AGEIX_BASE_URL="${AGEIX_BASE_URL:-http://127.0.0.1:8002}"
PROJECT_ID="${PROJECT_ID:-Ageix}"
SESSION_ID="kc-provision-connector-${CONNECTOR_ID}-$(date +%s)"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

REDIRECT_URIS_JSON="$(printf '%s\n' "${REDIRECT_URIS[@]}" | python3 -c "import json, sys; print(json.dumps([l.rstrip(chr(10)) for l in sys.stdin]))")"

python3 -c "
import json
print(json.dumps({
    'context': {'session_id': '${SESSION_ID}', 'project_id': '${PROJECT_ID}'},
    'capability_id': 'identity.keycloak.connector.provision',
    'arguments': {'connector_id': '${CONNECTOR_ID}', 'redirect_uris': json.loads('''${REDIRECT_URIS_JSON}''')},
}))
" > "${WORKDIR}/payload.json"

curl -sS -X POST "${AGEIX_BASE_URL}/capabilities/execute" \
  -H "Authorization: Bearer ${AGEIX_CHAIR_ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @"${WORKDIR}/payload.json" | python3 -m json.tool
