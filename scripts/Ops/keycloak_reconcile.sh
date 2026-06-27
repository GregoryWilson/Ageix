#!/usr/bin/env bash
# Calls identity.keycloak.reconcile against the governed boundary using the
# chair-admin token already present in the environment -- no token paste.
#
# Usage: scripts/Ops/keycloak_reconcile.sh [session_id]
set -euo pipefail

if [[ -z "${AGEIX_CHAIR_ADMIN_TOKEN:-}" ]]; then
  echo "ERROR: AGEIX_CHAIR_ADMIN_TOKEN is not set in the environment." >&2
  exit 2
fi

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
