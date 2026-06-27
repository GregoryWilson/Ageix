#!/usr/bin/env bash
# Exchanges a provisioned MCP client's secret for a fresh access token and
# verifies it end-to-end against the governed boundary -- no manual token
# copy/paste. Reads the client secret straight from the file the
# provisioning capability already wrote to disk.
#
# Usage: scripts/Ops/verify_mcp_client_oauth.sh <client_id> [session_id]
#   e.g. scripts/Ops/verify_mcp_client_oauth.sh claude
#
# Env overrides:
#   REPO_ROOT            repo root containing .ageix/ (default: cwd)
#   KEYCLOAK_ISSUER_URL  realm issuer URL (default: https://auth.wilsongpt.com/realms/ageix)
#   AGEIX_BASE_URL       governed boundary base URL (default: http://127.0.0.1:8002)
#   PROJECT_ID           project id used in the test capability call (default: Ageix)
set -euo pipefail

CLIENT_ID="${1:-}"
if [[ -z "$CLIENT_ID" ]]; then
  echo "Usage: $0 <client_id> [session_id]" >&2
  echo "  e.g. $0 claude" >&2
  exit 2
fi

REPO_ROOT="${REPO_ROOT:-$(pwd)}"
SECRET_FILE="${REPO_ROOT}/.ageix/instance/keycloak/${CLIENT_ID}.json"
if [[ ! -f "$SECRET_FILE" ]]; then
  echo "ERROR: no provisioned secret found at ${SECRET_FILE}" >&2
  echo "Run scripts/Ops/provision_mcp_client.sh ${CLIENT_ID} first." >&2
  exit 2
fi

KEYCLOAK_ISSUER_URL="${KEYCLOAK_ISSUER_URL:-https://auth.wilsongpt.com/realms/ageix}"
AGEIX_BASE_URL="${AGEIX_BASE_URL:-http://127.0.0.1:8002}"
PROJECT_ID="${PROJECT_ID:-Ageix}"
SESSION_ID="${2:-oauth-verify-${CLIENT_ID}-$(date +%s)}"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

python3 -c "
import json
data = json.load(open('${SECRET_FILE}'))
print(data['keycloak_client_id'])
print(data['client_secret'])
" > "${WORKDIR}/creds.txt"

KEYCLOAK_CLIENT_ID="$(sed -n '1p' "${WORKDIR}/creds.txt")"
CLIENT_SECRET="$(sed -n '2p' "${WORKDIR}/creds.txt")"

echo "== Exchanging client_credentials for ${KEYCLOAK_CLIENT_ID} =="
curl -sS -X POST "${KEYCLOAK_ISSUER_URL}/protocol/openid-connect/token" \
  -d "grant_type=client_credentials" \
  -d "client_id=${KEYCLOAK_CLIENT_ID}" \
  -d "client_secret=${CLIENT_SECRET}" \
  > "${WORKDIR}/token_response.json"

ACCESS_TOKEN="$(python3 -c "
import json, sys
payload = json.load(open('${WORKDIR}/token_response.json'))
if 'access_token' not in payload:
    print('TOKEN_EXCHANGE_FAILED: ' + json.dumps(payload), file=sys.stderr)
    sys.exit(1)
print(payload['access_token'])
")"

echo
echo "== Decoded token claims =="
python3 -c "
import base64, json
token = '''${ACCESS_TOKEN}'''
segment = token.split('.')[1]
segment += '=' * (-len(segment) % 4)
claims = json.loads(base64.urlsafe_b64decode(segment))
print(json.dumps({k: claims.get(k) for k in ('iss', 'azp', 'agent_id', 'exp')}, indent=2))
"

echo
echo "== GET /health =="
curl -sS "${AGEIX_BASE_URL}/health" -H "Authorization: Bearer ${ACCESS_TOKEN}" | python3 -m json.tool

python3 -c "
import json
print(json.dumps({'context': {'session_id': '${SESSION_ID}', 'project_id': '${PROJECT_ID}'}, 'capability_id': 'ageix.health', 'arguments': {}}))
" > "${WORKDIR}/payload.json"

echo
echo "== POST /capabilities/execute (ageix.health) =="
curl -sS -X POST "${AGEIX_BASE_URL}/capabilities/execute" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @"${WORKDIR}/payload.json" | python3 -m json.tool
