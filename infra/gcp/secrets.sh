#!/usr/bin/env bash
# Loads the three secrets into Secret Manager from the macOS login keychain.
# Values never hit the terminal: each one is piped straight into gcloud.
#
# Keychain entries (account dylanmerigaud, service name = secret name):
#   grafana-sa-token       Grafana service account token, Editor role on the stack
#   grafana-influx-token   Grafana Cloud access policy token, scopes metrics:write and logs:write
#   airlock-mcp-token      the bearer mcp-grafana enforces on its HTTP transport (generated here if absent)
set -euo pipefail

PROJECT="${AIRLOCK_PROJECT:-airlock-agentic-cinema}"
ACCOUNT_KC="dylanmerigaud"

upsert() {
  local name="$1"
  if ! gcloud secrets describe "$name" --project="$PROJECT" >/dev/null 2>&1; then
    gcloud secrets create "$name" --project="$PROJECT" --replication-policy=automatic >/dev/null
  fi
  gcloud secrets versions add "$name" --project="$PROJECT" --data-file=- >/dev/null
  echo "secret $name: new version added (length $(security find-generic-password -s "$name" -a "$ACCOUNT_KC" -w | tr -d '\n' | wc -c | tr -d ' '))"
}

if ! security find-generic-password -s airlock-mcp-token -a "$ACCOUNT_KC" >/dev/null 2>&1; then
  openssl rand -hex 32 | tr -d '\n' | xargs -0 security add-generic-password -s airlock-mcp-token -a "$ACCOUNT_KC" -U -w
  echo "generated airlock-mcp-token in the keychain"
fi

for name in grafana-sa-token grafana-influx-token airlock-mcp-token; do
  security find-generic-password -s "$name" -a "$ACCOUNT_KC" -w | tr -d '\n' | upsert "$name"
done
