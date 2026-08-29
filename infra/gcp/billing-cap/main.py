"""Budget cap: when the budget's Pub/Sub message says the cost reached the budget, detach the
project from its billing account. Google's documented "disable billing to stop usage" pattern.

The budget counts GROSS cost (credits excluded), so the trigger point is where the hackathon
credit would be exhausted and real money would start. Re-attaching billing is a manual act.
"""

from __future__ import annotations

import base64
import json
import os

import functions_framework
from google.cloud import billing_v1

PROJECT = os.environ.get("CAP_PROJECT", "airlock-agentic-cinema")
RATIO = float(os.environ.get("CAP_RATIO", "1.0"))


@functions_framework.cloud_event
def cap(event):
    data = json.loads(base64.b64decode(event.data["message"]["data"]).decode())
    cost = float(data.get("costAmount", 0))
    budget = float(data.get("budgetAmount", 0))
    print(json.dumps({"cost": cost, "budget": budget, "interval": data.get("costIntervalStart")}))
    if budget <= 0 or cost < budget * RATIO:
        return
    client = billing_v1.CloudBillingClient()
    name = f"projects/{PROJECT}"
    info = client.get_project_billing_info(name=name)
    if not info.billing_enabled:
        print("billing already disabled")
        return
    client.update_project_billing_info(name=name, project_billing_info=billing_v1.ProjectBillingInfo(billing_account_name=""))
    print(json.dumps({"action": "billing disabled", "project": PROJECT, "cost": cost, "budget": budget}))
