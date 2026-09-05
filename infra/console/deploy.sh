#!/usr/bin/env bash
# Deploy the Airlock reviewer console to Cloud Run from source.
# The Cloud Run default service account already holds the roles the console needs:
# Vertex AI user (streamQuery), Storage object admin (uploads and previews) and
# Secret Manager secret accessor (the Grafana service account token).
#
# Usage:
#   export AGENT_ENGINE_RESOURCE=projects/771466810465/locations/us-central1/reasoningEngines/<id>
#   bash infra/console/deploy.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

: "${AGENT_ENGINE_RESOURCE:?Set AGENT_ENGINE_RESOURCE to the deployed reasoning engine resource name}"

PROJECT="${GOOGLE_CLOUD_PROJECT:-airlock-agentic-cinema}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
BUCKET="${AIRLOCK_ASSETS_BUCKET:-airlock-agentic-cinema-assets}"
GRAFANA_URL="${GRAFANA_URL:-https://narrowsubmarine1895.grafana.net}"
GRAFANA_PROM_UID="${GRAFANA_PROM_UID:-grafanacloud-prom}"
GRAFANA_TEMPO_UID="${GRAFANA_TEMPO_UID:-grafanacloud-traces}"
DASHBOARD_URL="${AIRLOCK_PUBLIC_DASHBOARD_URL:-https://narrowsubmarine1895.grafana.net/public-dashboards/97860661238c4536a743e0d858aef845}"

ENV_VARS="AGENT_ENGINE_RESOURCE=${AGENT_ENGINE_RESOURCE}"
ENV_VARS="${ENV_VARS},GOOGLE_CLOUD_PROJECT=${PROJECT}"
ENV_VARS="${ENV_VARS},AIRLOCK_ASSETS_BUCKET=${BUCKET}"
ENV_VARS="${ENV_VARS},GRAFANA_URL=${GRAFANA_URL}"
ENV_VARS="${ENV_VARS},GRAFANA_PROM_UID=${GRAFANA_PROM_UID}"
ENV_VARS="${ENV_VARS},GRAFANA_TEMPO_UID=${GRAFANA_TEMPO_UID}"
ENV_VARS="${ENV_VARS},AIRLOCK_PUBLIC_DASHBOARD_URL=${DASHBOARD_URL}"
ENV_VARS="${ENV_VARS},AIRLOCK_MOCK=0"

gcloud run deploy airlock-console \
  --source console \
  --project "$PROJECT" \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi \
  --max-instances 3 \
  --cpu 1 \
  --timeout 900 \
  --set-env-vars "$ENV_VARS" \
  --set-secrets GRAFANA_SERVICE_ACCOUNT_TOKEN=grafana-sa-token:latest

gcloud run services describe airlock-console \
  --project "$PROJECT" --region "$REGION" \
  --format='value(status.url)'
