#!/usr/bin/env bash
# Creates the Google Cloud project for Airlock and enables what the build needs.
# Idempotent: every step tolerates "already exists".
# Account: dylanmerigaud@gmail.com only. Billing: the redeemed hackathon credit.
set -euo pipefail

PROJECT="${AIRLOCK_PROJECT:-airlock-agentic-cinema}"
BILLING="${AIRLOCK_BILLING:-012DF6-79381F-D64642}"
REGION="${AIRLOCK_REGION:-us-central1}"
ACCOUNT="${AIRLOCK_ACCOUNT:-dylanmerigaud@gmail.com}"

active="$(gcloud auth list --filter=status:ACTIVE --format='value(account)')"
if [[ "$active" != "$ACCOUNT" ]]; then
  echo "active gcloud account is '$active', expected '$ACCOUNT'. Run: gcloud auth login $ACCOUNT" >&2
  exit 1
fi

gcloud projects describe "$PROJECT" >/dev/null 2>&1 || gcloud projects create "$PROJECT" --name="Airlock"
gcloud billing projects link "$PROJECT" --billing-account="$BILLING"
gcloud config set project "$PROJECT" >/dev/null

gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  videointelligence.googleapis.com \
  logging.googleapis.com \
  storage.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
BUCKET="gs://${PROJECT}-staging"
gcloud storage buckets describe "$BUCKET" >/dev/null 2>&1 || gcloud storage buckets create "$BUCKET" --location="$REGION" --uniform-bucket-level-access

# Service agents: the Agent Engine one reads Secret Manager; the Cloud Run runtime SA reads it too.
gcloud beta services identity create --service=aiplatform.googleapis.com --project="$PROJECT" >/dev/null 2>&1 || true
AE_SA="service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
RUN_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for sa in "$AE_SA" "$RUN_SA"; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:${sa}" --role="roles/secretmanager.secretAccessor" --condition=None >/dev/null 2>&1 \
    || echo "note: could not bind ${sa} yet (service agent may not exist until first use); rerun after the first Agent Engine deploy"
done

echo "project=$PROJECT number=$PROJECT_NUMBER region=$REGION bucket=$BUCKET"
echo "agent engine service agent: $AE_SA"
