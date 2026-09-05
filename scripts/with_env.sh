#!/usr/bin/env bash
# Runs a command with .env.local loaded and the secrets pulled from the macOS keychain.
# Secrets never touch a file: they go from the keychain into the child's environment only.
#   scripts/with_env.sh uv run python -m airlock.run assets/real/CrestToothpa-18-48.mp4
#
# The keychain account is AIRLOCK_KEYCHAIN_ACCOUNT (default dylanmerigaud, airlock/settings.py names
# the same default). On a machine with no keychain, export the four variables below instead and run
# the command directly; a variable already set in the environment is kept as is.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -a
# shellcheck disable=SC1091
[[ -f "$ROOT/.env.local" ]] && source "$ROOT/.env.local"
set +a
ACCOUNT_KC="${AIRLOCK_KEYCHAIN_ACCOUNT:-dylanmerigaud}"
kc() { security find-generic-password -s "$1" -a "$ACCOUNT_KC" -w 2>/dev/null | tr -d '\n'; }
export GRAFANA_SERVICE_ACCOUNT_TOKEN="${GRAFANA_SERVICE_ACCOUNT_TOKEN:-$(kc grafana-sa-token)}"
export GRAFANA_INFLUX_TOKEN="${GRAFANA_INFLUX_TOKEN:-$(kc grafana-influx-token)}"
export GRAFANA_LOKI_TOKEN="${GRAFANA_LOKI_TOKEN:-$GRAFANA_INFLUX_TOKEN}"
export AIRLOCK_MCP_TOKEN="${AIRLOCK_MCP_TOKEN:-$(kc airlock-mcp-token)}"
exec "$@"
