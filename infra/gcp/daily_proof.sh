#!/usr/bin/env bash
# The daily proof on a schedule: a Cloud Run job (airlock-daily-proof) that calibrates every gate and
# runs the clean clip through the deployed pipeline (airlock/daily_proof.py), and a Cloud Scheduler
# job of the same name that runs it every 12 hours through the Cloud Run Admin API.
#
# Every step is idempotent: run it again after a code change and only the image and the job move.
# The job runs as the project's default compute service account (the roles airlock-mcp already
# uses: Vertex AI user, Storage object admin, Secret Manager accessor); the scheduler runs as its
# own service account, daily-proof-scheduler@, which holds roles/run.invoker on this job only.
#
# Usage: bash infra/gcp/daily_proof.sh
#   AGENT_ENGINE_RESOURCE   the reasoning engine the proof queries (default: the deployed pipeline)
# The coordinates below are the same variables airlock/settings.py reads, with the same defaults.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROJECT="${AIRLOCK_PROJECT:-airlock-agentic-cinema}"
REGION="${AIRLOCK_REGION:-us-central1}"
BUCKET="${AIRLOCK_ASSETS_BUCKET:-airlock-agentic-cinema-assets}"
JOB="${AIRLOCK_PROOF_JOB:-airlock-daily-proof}"
REPOSITORY="${AIRLOCK_ARTIFACT_REPO:-airlock}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPOSITORY}/airlock-daily-proof:latest"
ENGINE="${AGENT_ENGINE_RESOURCE:-projects/771466810465/locations/us-central1/reasoningEngines/1737023312967499776}"
SCHEDULE="${AIRLOCK_PROOF_SCHEDULE:-0 */12 * * *}"
GRAFANA_INFLUX_URL="${GRAFANA_INFLUX_URL:-https://prometheus-prod-67-prod-us-west-0.grafana.net/api/v1/push/influx/write}"
GRAFANA_INFLUX_USER="${GRAFANA_INFLUX_USER:-3546988}"
GRAFANA_LOKI_URL="${GRAFANA_LOKI_URL:-https://logs-prod-021.grafana.net}"
GRAFANA_LOKI_USER="${GRAFANA_LOKI_USER:-1769169}"
SCHEDULER_SA_ID="daily-proof-scheduler"
SCHEDULER_SA="${SCHEDULER_SA_ID}@${PROJECT}.iam.gserviceaccount.com"

# Step 1: the APIs, enabled once.
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  --project="$PROJECT" >/dev/null
echo "apis: run, cloudscheduler, cloudbuild, artifactregistry enabled"

# Step 2: the Artifact Registry repository, created once (shared with airlock-mcp).
if ! gcloud artifacts repositories describe "$REPOSITORY" --project="$PROJECT" --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$REPOSITORY" --project="$PROJECT" --location="$REGION" --repository-format=docker \
    --description="Airlock service images" >/dev/null
  echo "artifact registry repository $REPOSITORY created in $REGION"
fi

# Step 3: build. Cloud Build's --tag shortcut wants a file literally named "Dockerfile" at the root of
# the submitted source; the repo's is Dockerfile.proof, so a small build context is assembled with
# that rename, the same way infra/airlock-mcp/deploy.sh does it.
BUILD_CTX="$(mktemp -d)"
trap 'rm -rf "$BUILD_CTX"' EXIT
cp "$REPO_ROOT/Dockerfile.proof" "$BUILD_CTX/Dockerfile"
cp "$REPO_ROOT/pyproject.toml" "$REPO_ROOT/uv.lock" "$BUILD_CTX/"
cp -R "$REPO_ROOT/airlock" "$REPO_ROOT/rules" "$REPO_ROOT/trust" "$BUILD_CTX/"
cp "$REPO_ROOT/charter.yaml" "$REPO_ROOT/rights-registry.yaml" "$REPO_ROOT/pricing.yaml" "$BUILD_CTX/"
find "$BUILD_CTX" -name __pycache__ -type d -prune -exec rm -rf {} +

gcloud builds submit --project="$PROJECT" --tag="$IMAGE" "$BUILD_CTX"

# Step 4: the job (deploy creates it or updates it). One task, 30 minutes (the rights gate's Video
# Intelligence call alone can take three minutes when calls contend), no retry: a failed proof stays a
# failed proof. With one retry, the two proofs that met a paused Grafana Cloud stack (2026-09-04 12:05
# UTC and 2026-09-05 00:04 UTC) were retried into passes; the verdict now waits for the stack itself.
gcloud run jobs deploy "$JOB" \
  --project="$PROJECT" --region="$REGION" \
  --image="$IMAGE" \
  --tasks=1 --task-timeout=1800 --cpu=1 --memory=2Gi --max-retries=0 \
  --set-env-vars="AIRLOCK_PROJECT=${PROJECT},AIRLOCK_ASSETS_BUCKET=${BUCKET},AIRLOCK_RUNTIME=daily-proof,AGENT_ENGINE_RESOURCE=${ENGINE},GRAFANA_INFLUX_URL=${GRAFANA_INFLUX_URL},GRAFANA_INFLUX_USER=${GRAFANA_INFLUX_USER},GRAFANA_LOKI_URL=${GRAFANA_LOKI_URL},GRAFANA_LOKI_USER=${GRAFANA_LOKI_USER}" \
  --set-secrets="GRAFANA_INFLUX_TOKEN=grafana-influx-token:latest,GRAFANA_LOKI_TOKEN=grafana-influx-token:latest" \
  --quiet

# Step 5: the scheduler's own service account, with the right to run this job and nothing else.
if ! gcloud iam service-accounts describe "$SCHEDULER_SA" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SCHEDULER_SA_ID" --project="$PROJECT" \
    --display-name="Airlock daily proof scheduler" >/dev/null
  echo "service account $SCHEDULER_SA created"
fi
gcloud run jobs add-iam-policy-binding "$JOB" --project="$PROJECT" --region="$REGION" \
  --member="serviceAccount:${SCHEDULER_SA}" --role="roles/run.invoker" --quiet >/dev/null
echo "$SCHEDULER_SA holds roles/run.invoker on job $JOB"

# Step 6: the schedule. The target is the Cloud Run Admin API's :run endpoint, a Google API, which
# takes an OAuth access token minted for the scheduler's service account (an OIDC identity token is
# what a Cloud Run service would take; the Admin API refuses it).
RUN_URI="https://run.googleapis.com/v2/projects/${PROJECT}/locations/${REGION}/jobs/${JOB}:run"
SCHEDULER_ARGS=(--project="$PROJECT" --location="$REGION" --schedule="$SCHEDULE" --time-zone="Etc/UTC"
  --uri="$RUN_URI" --http-method=POST --oauth-service-account-email="$SCHEDULER_SA"
  --description="Airlock daily proof: calibrate every gate and run the clean clip through the pipeline"
  --attempt-deadline=180s --max-retry-attempts=0)
if gcloud scheduler jobs describe "$JOB" --project="$PROJECT" --location="$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$JOB" "${SCHEDULER_ARGS[@]}" >/dev/null
  echo "scheduler job $JOB updated: $SCHEDULE UTC"
else
  gcloud scheduler jobs create http "$JOB" "${SCHEDULER_ARGS[@]}" >/dev/null
  echo "scheduler job $JOB created: $SCHEDULE UTC"
fi

gcloud scheduler jobs describe "$JOB" --project="$PROJECT" --location="$REGION" \
  --format='value(name,schedule,timeZone,httpTarget.uri,httpTarget.oauthToken.serviceAccountEmail,state)'
echo "run once by hand:  gcloud run jobs execute $JOB --project=$PROJECT --region=$REGION --wait"
echo "fire the schedule: gcloud scheduler jobs run $JOB --project=$PROJECT --location=$REGION"
