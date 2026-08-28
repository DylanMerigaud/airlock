#!/usr/bin/env bash
# Runs a command with .env.local loaded and the secrets pulled from the macOS keychain.
# Secrets never touch a file: they go from the keychain into the child's environment only.
#   scripts/with_env.sh uv run adk run agents/spike "run the spike"
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -a
# shellcheck disable=SC1091
source "$ROOT/.env.local"
set +a
kc() { security find-generic-password -s "$1" -a dylanmerigaud -w 2>/dev/null | tr -d '\n'; }
export GRAFANA_SERVICE_ACCOUNT_TOKEN="$(kc grafana-sa-token)"
export GRAFANA_INFLUX_TOKEN="$(kc grafana-influx-token)"
export GRAFANA_LOKI_TOKEN="$GRAFANA_INFLUX_TOKEN"
export AIRLOCK_MCP_TOKEN="$(kc airlock-mcp-token)"
exec "$@"
