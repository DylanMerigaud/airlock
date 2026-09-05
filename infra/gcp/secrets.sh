#!/usr/bin/env bash
# Loads the three secrets into Secret Manager. Values never hit the terminal: each one is piped
# straight into gcloud.
#
# Where each value comes from, in order:
#   1. the environment variable named below, when set (a Linux judge, a CI runner);
#   2. the macOS login keychain, account AIRLOCK_KEYCHAIN_ACCOUNT (default dylanmerigaud), service
#      name = secret name, when the `security` command exists and the entry does;
#   3. a prompt on the terminal, read without echo, when there is a terminal;
#   4. for airlock-mcp-token only: a fresh random bearer, generated here and stored in the keychain
#      when there is one (the agents read it back from Secret Manager, never from this machine).
#
#   secret name            env variable                    what it is
#   grafana-sa-token       GRAFANA_SERVICE_ACCOUNT_TOKEN   Grafana service account token, Editor role on the stack
#   grafana-influx-token   GRAFANA_INFLUX_TOKEN            Grafana Cloud access policy token, scopes metrics:write and logs:write
#   airlock-mcp-token      AIRLOCK_MCP_TOKEN               the bearer mcp-grafana enforces on its HTTP transport
#
# Usage: bash infra/gcp/secrets.sh
#        GRAFANA_SERVICE_ACCOUNT_TOKEN=... GRAFANA_INFLUX_TOKEN=... bash infra/gcp/secrets.sh   # no keychain
set -euo pipefail

PROJECT="${AIRLOCK_PROJECT:-airlock-agentic-cinema}"
ACCOUNT_KC="${AIRLOCK_KEYCHAIN_ACCOUNT:-dylanmerigaud}"

have_keychain() { command -v security >/dev/null 2>&1; }

kc_read() { security find-generic-password -s "$1" -a "$ACCOUNT_KC" -w 2>/dev/null | tr -d '\n'; }

kc_store() {  # $1 name, value on stdin
  tr -d '\n' | xargs -0 security add-generic-password -s "$1" -a "$ACCOUNT_KC" -U -w
}

env_name() {
  case "$1" in
    grafana-sa-token) echo GRAFANA_SERVICE_ACCOUNT_TOKEN ;;
    grafana-influx-token) echo GRAFANA_INFLUX_TOKEN ;;
    airlock-mcp-token) echo AIRLOCK_MCP_TOKEN ;;
    *) echo "unknown secret $1" >&2; return 1 ;;
  esac
}

# Prints the value of secret $1 on stdout (the only place it ever goes), and where it came from on stderr.
value_of() {
  local name="$1" var value
  var="$(env_name "$name")"
  value="${!var:-}"
  if [[ -n "$value" ]]; then
    echo "secret $name: from \$$var" >&2
    printf '%s' "$value"
    return 0
  fi
  if have_keychain && value="$(kc_read "$name")" && [[ -n "$value" ]]; then
    echo "secret $name: from the keychain (account $ACCOUNT_KC)" >&2
    printf '%s' "$value"
    return 0
  fi
  if [[ "$name" == "airlock-mcp-token" ]]; then
    value="$(openssl rand -hex 32 | tr -d '\n')"
    if have_keychain; then
      printf '%s' "$value" | kc_store "$name"
      echo "secret $name: generated and stored in the keychain (account $ACCOUNT_KC)" >&2
    else
      echo "secret $name: generated (no keychain here; the services read it from Secret Manager)" >&2
    fi
    printf '%s' "$value"
    return 0
  fi
  if [[ -t 0 ]]; then
    read -r -s -p "value for $name (\$$var; not echoed): " value </dev/tty
    echo >&2
    [[ -n "$value" ]] || { echo "secret $name: nothing entered" >&2; return 1; }
    printf '%s' "$value"
    return 0
  fi
  echo "secret $name: set \$$var (no keychain entry, no terminal to ask on)" >&2
  return 1
}

upsert() {  # $1 name, value on stdin
  local name="$1"
  if ! gcloud secrets describe "$name" --project="$PROJECT" >/dev/null 2>&1; then
    gcloud secrets create "$name" --project="$PROJECT" --replication-policy=automatic >/dev/null
  fi
  gcloud secrets versions add "$name" --project="$PROJECT" --data-file=- >/dev/null
}

for name in grafana-sa-token grafana-influx-token airlock-mcp-token; do
  value="$(value_of "$name")"
  printf '%s' "$value" | upsert "$name"
  echo "secret $name: new version added (length ${#value})"
done
