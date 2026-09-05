#!/usr/bin/env bash
# The recording-day preparation, in the order docs/VIDEO-SCRIPT.md asks for. Prints what it measured.
#   scripts/demo_prep.sh            # calibrate every gate, check the hosted services, time the Crest run once
#   scripts/demo_prep.sh --no-time  # skip the timing run
#   scripts/demo_prep.sh --proof    # step 2 runs the daily proof instead (calibration plus the clean clip
#                                   # through Agent Engine, the same module the Cloud Run job runs every 12 h)
set -euo pipefail
NO_TIME=0
PROOF=0
for arg in "$@"; do
  case "$arg" in
    --no-time) NO_TIME=1 ;;
    --proof) PROOF=1 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# The same variables airlock/settings.py reads, with the same defaults.
CONSOLE="${AIRLOCK_CONSOLE_URL:-https://airlock-console-771466810465.us-central1.run.app}"
MCP="${AIRLOCK_MCP_SERVER_URL:-https://airlock-mcp-771466810465.us-central1.run.app/mcp}"
MCP_GRAFANA="${AIRLOCK_MCP_URL:-https://airlock-mcp-grafana-771466810465.us-central1.run.app/mcp}"
ENGINE="${AGENT_ENGINE_RESOURCE:-projects/771466810465/locations/us-central1/reasoningEngines/1737023312967499776}"
BUCKET="${AIRLOCK_ASSETS_BUCKET:-airlock-agentic-cinema-assets}"

echo "== 1. assets present and hashed"
bash scripts/fetch_assets.sh | tail -8

if [[ "$PROOF" == "1" ]]; then
  echo "== 2. daily proof (every gate CAUGHT, then the clean clip must PASS; exit 1 otherwise)"
  scripts/with_env.sh uv run python -m airlock.daily_proof 2>&1 | grep -vE "UserWarning|check_feature|AFC|WARNING" || echo "daily proof exit $?"
else
  echo "== 2. calibration ledger (every gate must read CAUGHT; the Cloud Run job airlock-daily-proof does this at 00:00 and 12:00 UTC)"
  scripts/with_env.sh uv run python -m airlock.calibrate 2>&1 | grep -vE "UserWarning|check_feature|AFC|WARNING"
fi

echo "== 3. hosted services"
printf 'console page: %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "$CONSOLE/")"
curl -s "$CONSOLE/api/health" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("console health:", "ok" if d.get("ok") else d.get("error"), [(g["gate"], g["state"]) for g in d.get("gates", [])])'
curl -s "$CONSOLE/api/stats" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("console stats:", {k: d.get(k) for k in ("checked_7d","blocked_7d","passed_7d","gates_calibrated","incidents_7d","cost_per_check_usd_7d")})'
printf 'mcp-grafana bearer check: %s (401 expected without a bearer)\n' "$(curl -s -o /dev/null -w '%{http_code}' -H 'Accept: application/json, text/event-stream' -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"prep","version":"0"}}}' "$MCP_GRAFANA")"
printf 'airlock-mcp bearer check: %s (401 expected without a bearer)\n' "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$MCP")"

if [[ "$NO_TIME" == "0" ]]; then
  echo "== 4. one timed Crest run from Agent Engine (the script wants three, alone, under 70 s each)"
  uv run python scripts/query_agent_engine.py "$ENGINE" "gs://${BUCKET}/real/CrestToothpa-18-48.mp4" 2>&1 | grep -E "rights_gate|VERDICT|done in" | cut -c1-160
fi

echo "== 5. reminders"
echo "- mute the rights gate in the console at least 16 minutes before the 'control unavailable' beat"
echo "- close every browser tab but the console, notifications off, 1920x1080 at 30 fps"
echo "- the PASS at the end needs every gate CAUGHT above and the clean clip"
