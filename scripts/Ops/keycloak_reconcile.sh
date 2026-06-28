#!/usr/bin/env bash
# Calls identity.keycloak.reconcile against the governed boundary, minting a
# fresh chair-admin token from Keycloak via the durable client credentials --
# no token paste.
#
# Usage: scripts/Ops/keycloak_reconcile.sh [session_id]
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

echo "Fetching admin token from Keycloak..." >&2
fetch_chair_admin_token

AGEIX_BASE_URL="${AGEIX_BASE_URL:-http://127.0.0.1:8002}"
PROJECT_ID="${PROJECT_ID:-Ageix}"
SESSION_ID="${1:-kc-reconcile-$(date +%s)}"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

python3 -c "
import json
print(json.dumps({'context': {'session_id': '${SESSION_ID}', 'project_id': '${PROJECT_ID}'}, 'capability_id': 'identity.keycloak.reconcile', 'arguments': {}}))
" > "${WORKDIR}/payload.json"

curl -sS -X POST "${AGEIX_BASE_URL}/capabilities/execute" \
  -H "Authorization: Bearer ${AGEIX_CHAIR_ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @"${WORKDIR}/payload.json" | python3 -m json.tool
