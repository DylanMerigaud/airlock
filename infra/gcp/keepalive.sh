#!/usr/bin/env bash
# The Grafana Cloud free stack pauses after idle hours and answers 503 "Your instance is loading" for
# about two minutes when something finally calls it. Measured twice on the daily proof (2026-09-04
# 12:05 UTC and 2026-09-05 00:04 UTC): the verdict agent's first Grafana call hit the paused stack,
# the proof failed on its first try and passed on the retry four minutes later. This job keeps the
# stack awake with real Grafana activity: every 30 minutes Cloud Scheduler GETs the console's
# /api/health, which runs the four gates' PromQL through Grafana's datasource query API.
#
# Usage: bash infra/gcp/keepalive.sh
set -euo pipefail

PROJECT="${AIRLOCK_PROJECT:-airlock-agentic-cinema}"
REGION="${AIRLOCK_REGION:-us-central1}"
CONSOLE="${AIRLOCK_CONSOLE_URL:-https://airlock-console-771466810465.us-central1.run.app}"
JOB="airlock-grafana-keepalive"
SCHEDULE="*/30 * * * *"

gcloud services enable cloudscheduler.googleapis.com --project="$PROJECT" >/dev/null

if gcloud scheduler jobs describe "$JOB" --project="$PROJECT" --location="$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$JOB" --project="$PROJECT" --location="$REGION" \
    --schedule="$SCHEDULE" --time-zone="Etc/UTC" --uri="$CONSOLE/api/health" --http-method=GET \
    --attempt-deadline=120s >/dev/null
  echo "scheduler job $JOB updated: $SCHEDULE UTC -> $CONSOLE/api/health"
else
  gcloud scheduler jobs create http "$JOB" --project="$PROJECT" --location="$REGION" \
    --schedule="$SCHEDULE" --time-zone="Etc/UTC" --uri="$CONSOLE/api/health" --http-method=GET \
    --attempt-deadline=120s >/dev/null
  echo "scheduler job $JOB created: $SCHEDULE UTC -> $CONSOLE/api/health"
fi

gcloud scheduler jobs describe "$JOB" --project="$PROJECT" --location="$REGION" \
  --format='value(name,schedule,httpTarget.uri,state)'
echo "run once by hand: gcloud scheduler jobs run $JOB --project=$PROJECT --location=$REGION"
