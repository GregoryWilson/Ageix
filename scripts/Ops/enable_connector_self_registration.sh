#!/usr/bin/env bash
# Calls identity.keycloak.connector.enable_self_registration to turn on RFC 7591
# anonymous Dynamic Client Registration for this realm, gated to a set of
# trusted redirect-URI hosts -- lets a human-delegated connector (e.g.
# Claude.ai's "Add custom connector") self-register a public PKCE client on
# first connect, without an admin pre-provisioning step. Mints a fresh
# chair-admin token from Keycloak via the durable client credentials -- no
# token paste.
#
# Usage: scripts/Ops/enable_connector_self_registration.sh <trusted_host> [<trusted_host> ...]
#   e.g. scripts/Ops/enable_connector_self_registration.sh claude.ai
#
# Env vars:
#   MAX_CLIENTS  cap on self-registered clients (default: 1)
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

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 <trusted_host> [<trusted_host> ...]" >&2
  exit 2
fi
TRUSTED_HOSTS=("$@")

echo "Fetching admin token from Keycloak..." >&2
fetch_chair_admin_token

AGEIX_BASE_URL="${AGEIX_BASE_URL:-http://127.0.0.1:8002}"
PROJECT_ID="${PROJECT_ID:-Ageix}"
MAX_CLIENTS="${MAX_CLIENTS:-1}"
SESSION_ID="kc-enable-connector-self-registration-$(date +%s)"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

TRUSTED_HOSTS_JSON="$(printf '%s\n' "${TRUSTED_HOSTS[@]}" | python3 -c "import json, sys; print(json.dumps([l.rstrip(chr(10)) for l in sys.stdin]))")"

python3 -c "
import json
print(json.dumps({
    'context': {'session_id': '${SESSION_ID}', 'project_id': '${PROJECT_ID}'},
    'capability_id': 'identity.keycloak.connector.enable_self_registration',
    'arguments': {'trusted_hosts': json.loads('''${TRUSTED_HOSTS_JSON}'''), 'max_clients': ${MAX_CLIENTS}},
}))
" > "${WORKDIR}/payload.json"

curl -sS -X POST "${AGEIX_BASE_URL}/capabilities/execute" \
  -H "Authorization: Bearer ${AGEIX_CHAIR_ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @"${WORKDIR}/payload.json" | python3 -m json.tool
