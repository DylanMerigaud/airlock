#!/usr/bin/env bash
# Deploys the open-source mcp-grafana server on Cloud Run in streamable HTTP mode.
# Inbound auth is the server's own bearer (MCP_GRAFANA_SERVER_TOKEN, from Secret Manager),
# so the service is public at the network level and closed at the MCP level.
# Grafana credentials come from Secret Manager too; nothing is baked into the image.
set -euo pipefail

PROJECT="${AIRLOCK_PROJECT:-airlock-agentic-cinema}"
REGION="${AIRLOCK_REGION:-us-central1}"
SERVICE="${AIRLOCK_MCP_SERVICE:-airlock-mcp-grafana}"
IMAGE="${AIRLOCK_MCP_IMAGE:-docker.io/grafana/mcp-grafana:1.3.0}"
: "${GRAFANA_URL:?set GRAFANA_URL, e.g. https://<stack>.grafana.net}"

ENABLED_TOOLS="search,datasource,incident,prometheus,loki,dashboard,annotations"

deploy() {
  local allowed_hosts="$1"
  gcloud run deploy "$SERVICE" \
    --project="$PROJECT" --region="$REGION" --platform=managed \
    --image="$IMAGE" \
    --allow-unauthenticated \
    --port=8080 --cpu=1 --memory=512Mi --min-instances=0 --max-instances=2 --timeout=300 \
    --set-env-vars="GRAFANA_URL=${GRAFANA_URL}" \
    --set-secrets="GRAFANA_SERVICE_ACCOUNT_TOKEN=grafana-sa-token:latest,MCP_GRAFANA_SERVER_TOKEN=airlock-mcp-token:latest" \
    --args="^|^-t|streamable-http|-address|0.0.0.0:8080|-allowed-hosts|${allowed_hosts}|-enabled-tools|${ENABLED_TOOLS}|-log-level|info" \
    --quiet
}

# First pass accepts any Host so the service comes up; second pass pins the two real hostnames
# (Cloud Run serves both the legacy *.a.run.app URL and the deterministic *.run.app one).
deploy "*"
URL="$(gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" --format='value(status.url)')"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
DET_URL="https://${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
deploy "${URL#https://},${DET_URL#https://}"
echo "mcp-grafana url: ${DET_URL}/mcp (also ${URL}/mcp)"
