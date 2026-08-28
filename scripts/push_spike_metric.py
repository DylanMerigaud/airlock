"""M1 step 4: push one airlock_gate_runs_total{gate="spike"} sample through the Influx endpoint."""

from __future__ import annotations

import json
import time

from airlock.telemetry import InfluxPusher, line

if __name__ == "__main__":
    pusher = InfluxPusher.from_env()
    payload = line("airlock_gate", {"gate": "spike"}, {"runs_total": 1, "errors_total": 0, "last_success_ts": int(time.time())})
    status = pusher.push_lines([payload])
    print(json.dumps({"http_status": status, "line": payload}))
