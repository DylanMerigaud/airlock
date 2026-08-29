#!/usr/bin/env bash
# Budget with alerts, and a hard cap: a Cloud Function that detaches the project from the billing
# account when the GROSS cost (credits excluded) reaches the credit amount. Idempotent.
set -euo pipefail
PROJECT="${AIRLOCK_PROJECT:-airlock-agentic-cinema}"
BILLING="${AIRLOCK_BILLING:-012DF6-79381F-D64642}"
REGION="${AIRLOCK_REGION:-us-central1}"
CREDIT_UNITS="${AIRLOCK_CREDIT_UNITS:-87}"      # whole EUR: the credit is 87.79, the budget rounds DOWN so the cap fires before real money
CREDIT_NANOS="${AIRLOCK_CREDIT_NANOS:-0}"
TOPIC="billing-cap"
SA="billing-cap@${PROJECT}.iam.gserviceaccount.com"

gcloud pubsub topics describe "$TOPIC" --project="$PROJECT" >/dev/null 2>&1 || gcloud pubsub topics create "$TOPIC" --project="$PROJECT"

if ! gcloud billing budgets list --billing-account="$BILLING" --format="value(displayName)" | grep -qx "airlock hackathon credit"; then
  gcloud billing budgets create --billing-account="$BILLING" --display-name="airlock hackathon credit" \
    --budget-amount="${CREDIT_UNITS}EUR" \
    --filter-projects="projects/${PROJECT}" --credit-types-treatment=exclude-all-credits \
    --threshold-rule=percent=0.5 --threshold-rule=percent=0.75 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0 \
    --notifications-rule-pubsub-topic="projects/${PROJECT}/topics/${TOPIC}" 2>&1 | tail -2
fi

gcloud iam service-accounts describe "$SA" --project="$PROJECT" >/dev/null 2>&1 || gcloud iam service-accounts create billing-cap --project="$PROJECT" --display-name="billing cap function"
gcloud billing accounts add-iam-policy-binding "$BILLING" --member="serviceAccount:${SA}" --role="roles/billing.admin" >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:${SA}" --role="roles/billing.projectManager" --condition=None >/dev/null

gcloud functions deploy billing-cap --gen2 --project="$PROJECT" --region="$REGION" --runtime=python312 \
  --source="$(dirname "${BASH_SOURCE[0]}")/billing-cap" --entry-point=cap \
  --trigger-topic="$TOPIC" --service-account="$SA" --set-env-vars="CAP_PROJECT=${PROJECT},CAP_RATIO=1.0" \
  --memory=256Mi --max-instances=1 --quiet 2>&1 | grep -E "state|url|ERROR" | head -3

echo "budget:"; gcloud billing budgets list --billing-account="$BILLING" --format="table(displayName,amount.specifiedAmount.units,amount.specifiedAmount.nanos,thresholdRules[].thresholdPercent)"
