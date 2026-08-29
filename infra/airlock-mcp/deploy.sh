#!/usr/bin/env bash
# Builds and deploys airlock-mcp: Airlock's four gates as MCP tools, on Cloud Run.
# Inbound auth is the server's own bearer (AIRLOCK_MCP_SERVER_TOKEN, from Secret Manager), so the
# service is public at the network level and closed at the MCP level, the same pattern as
# infra/mcp-grafana/deploy.sh.
#
# Usage: bash infra/airlock-mcp/deploy.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROJECT="${AIRLOCK_PROJECT:-airlock-agentic-cinema}"
REGION="${AIRLOCK_REGION:-us-central1}"
SERVICE="${AIRLOCK_MCP_SERVICE:-airlock-mcp}"
REPOSITORY="${AIRLOCK_ARTIFACT_REPO:-airlock}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPOSITORY}/airlock-mcp:latest"
ACCOUNT_KC="dylanmerigaud"
SECRET_NAME="airlock-mcp-server-token"

# Step 1: the bearer, keychain first (never printed), Secret Manager second, both idempotent.
if ! security find-generic-password -s "$SECRET_NAME" -a "$ACCOUNT_KC" >/dev/null 2>&1; then
  openssl rand -hex 32 | tr -d '\n' | xargs -0 security add-generic-password -s "$SECRET_NAME" -a "$ACCOUNT_KC" -U -w
  echo "generated $SECRET_NAME in the keychain"
fi

if ! gcloud secrets describe "$SECRET_NAME" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud secrets create "$SECRET_NAME" --project="$PROJECT" --replication-policy=automatic >/dev/null
  security find-generic-password -s "$SECRET_NAME" -a "$ACCOUNT_KC" -w | tr -d '\n' | gcloud secrets versions add "$SECRET_NAME" --project="$PROJECT" --data-file=- >/dev/null
  echo "secret $SECRET_NAME created in Secret Manager"
else
  echo "secret $SECRET_NAME already in Secret Manager, left as is"
fi

# Step 2: the Artifact Registry repository, created once.
if ! gcloud artifacts repositories describe "$REPOSITORY" --project="$PROJECT" --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$REPOSITORY" --project="$PROJECT" --location="$REGION" --repository-format=docker \
    --description="Airlock service images" >/dev/null
  echo "artifact registry repository $REPOSITORY created in $REGION"
fi

# Step 3: build. Cloud Build's --tag shortcut always looks for a file literally named "Dockerfile" at
# the root of the submitted source, and this repo's is named Dockerfile.mcp to keep it apart from any
# other service's Dockerfile; a small build context is assembled with that rename instead of touching
# the tracked file.
BUILD_CTX="$(mktemp -d)"
trap 'rm -rf "$BUILD_CTX"' EXIT
cp "$REPO_ROOT/Dockerfile.mcp" "$BUILD_CTX/Dockerfile"
cp "$REPO_ROOT/pyproject.toml" "$REPO_ROOT/uv.lock" "$BUILD_CTX/"
cp -R "$REPO_ROOT/airlock" "$REPO_ROOT/airlock_mcp" "$REPO_ROOT/rules" "$REPO_ROOT/trust" "$BUILD_CTX/"
cp "$REPO_ROOT/charter.yaml" "$REPO_ROOT/rights-registry.yaml" "$BUILD_CTX/"

gcloud builds submit --project="$PROJECT" --tag="$IMAGE" "$BUILD_CTX"

# Step 4: deploy.
gcloud run deploy "$SERVICE" \
  --project="$PROJECT" --region="$REGION" \
  --image="$IMAGE" \
  --allow-unauthenticated \
  --port=8080 --memory=1Gi --cpu=1 --timeout=900 \
  --set-env-vars="AIRLOCK_PROJECT=airlock-agentic-cinema,AIRLOCK_ASSETS_BUCKET=airlock-agentic-cinema-assets,AIRLOCK_RUNTIME=airlock-mcp,GRAFANA_INFLUX_URL=https://prometheus-prod-67-prod-us-west-0.grafana.net/api/v1/push/influx/write,GRAFANA_INFLUX_USER=3546988,GRAFANA_LOKI_URL=https://logs-prod-021.grafana.net,GRAFANA_LOKI_USER=1769169" \
  --set-secrets="AIRLOCK_MCP_SERVER_TOKEN=airlock-mcp-server-token:latest,GRAFANA_INFLUX_TOKEN=grafana-influx-token:latest,GRAFANA_LOKI_TOKEN=grafana-influx-token:latest" \
  --quiet

URL="$(gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" --format='value(status.url)')"
echo "airlock-mcp url: ${URL}/mcp (health: ${URL}/healthz)"
