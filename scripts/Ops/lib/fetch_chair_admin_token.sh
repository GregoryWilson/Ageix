# Mints a fresh chair-admin bearer token from Keycloak via a client_credentials
# grant. Sourced by scripts/Ops/*.sh that need to call /capabilities/execute as
# chair-admin -- a token is something you derive from a secret at call time,
# not a static value you paste into .env, so this replaces a pre-set
# AGEIX_CHAIR_ADMIN_TOKEN with one minted on demand from the durable client
# credentials instead.
#
# Requires AGEIX_CHAIR_ADMIN_CLIENT_ID, AGEIX_CHAIR_ADMIN_SECRET,
# AGEIX_KEYCLOAK_URL, AGEIX_REALM in the environment (or repo-root .env).
# Exports AGEIX_CHAIR_ADMIN_TOKEN into the calling shell on success.

fetch_chair_admin_token() {
  for var in AGEIX_CHAIR_ADMIN_CLIENT_ID AGEIX_CHAIR_ADMIN_SECRET AGEIX_KEYCLOAK_URL AGEIX_REALM; do
    if [[ -z "${!var:-}" ]]; then
      echo "ERROR: $var is not set in the environment." >&2
      return 2
    fi
  done

  AGEIX_CHAIR_ADMIN_TOKEN="$(
    curl -sS -X POST \
      "${AGEIX_KEYCLOAK_URL}/realms/${AGEIX_REALM}/protocol/openid-connect/token" \
      -d "grant_type=client_credentials" \
      -d "client_id=${AGEIX_CHAIR_ADMIN_CLIENT_ID}" \
      -d "client_secret=${AGEIX_CHAIR_ADMIN_SECRET}" \
    | python3 -c "
import json, sys
data = json.load(sys.stdin)
token = data.get('access_token')
if not token:
    sys.exit(f'Token error: {data}')
print(token)
"
  )"
  export AGEIX_CHAIR_ADMIN_TOKEN
}
