"""Create the "Airlock gates" dashboard on the Grafana stack and print the Prometheus datasource uid.

Uses the Grafana HTTP API with the service account token (Editor). Idempotent:
the dashboard is upserted by uid.

Environment: GRAFANA_URL, GRAFANA_SERVICE_ACCOUNT_TOKEN.
"""

from __future__ import annotations

import json
import os
import sys

import httpx

DASHBOARD_UID = "airlock-gates"
GATES = ["rights", "claim", "brand", "provenance", "verdict", "spike"]


def _client() -> httpx.Client:
    url = os.environ.get("GRAFANA_URL", "").rstrip("/")
    token = os.environ.get("GRAFANA_SERVICE_ACCOUNT_TOKEN", "")
    if not url or not token:
        sys.exit("set GRAFANA_URL and GRAFANA_SERVICE_ACCOUNT_TOKEN")
    return httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=20)


def prometheus_uid(c: httpx.Client) -> str:
    r = c.get("/api/datasources")
    r.raise_for_status()
    for ds in r.json():
        if ds.get("type") == "prometheus":
            return ds["uid"]
    sys.exit("no prometheus datasource on this stack")


def panel(pid: int, title: str, expr: str, ds_uid: str, x: int, y: int, w: int = 12, h: int = 8, unit: str = "short", kind: str = "timeseries", legend: str = "{{gate}}") -> dict:
    return {
        "id": pid,
        "type": kind,
        "title": title,
        "datasource": {"type": "prometheus", "uid": ds_uid},
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "targets": [{"refId": "A", "expr": expr, "legendFormat": legend, "datasource": {"type": "prometheus", "uid": ds_uid}}],
    }


def dashboard(ds_uid: str) -> dict:
    return {
        "uid": DASHBOARD_UID,
        "title": "Airlock gates",
        "tags": ["airlock"],
        "timezone": "browser",
        "schemaVersion": 39,
        "time": {"from": "now-6h", "to": "now"},
        "refresh": "30s",
        "annotations": {
            "list": [
                {
                    "builtIn": 1,
                    "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                    "enable": True,
                    "hide": False,
                    "iconColor": "rgba(0, 211, 255, 1)",
                    "name": "Annotations & Alerts",
                    "type": "dashboard",
                },
                {
                    "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                    "enable": True,
                    "iconColor": "orange",
                    "name": "Airlock verdicts",
                    "target": {"limit": 100, "matchAny": False, "tags": ["airlock"], "type": "tags"},
                },
            ]
        },
        "panels": [
            panel(10, "Verdicts (7d)", "sum by (status, motive) (sum_over_time(airlock_verdict_total[7d]))", ds_uid, 0, 0, w=6, h=6, kind="stat", legend="{{status}} {{motive}}"),
            panel(11, "Calibration catches (7d)", "sum by (gate) (sum_over_time(airlock_calibration_catches_total[7d]))", ds_uid, 6, 0, w=6, h=6, kind="stat"),
            panel(12, "Calibration misses (7d)", "sum by (gate) (sum_over_time(airlock_calibration_misses_total[7d]))", ds_uid, 12, 0, w=6, h=6, kind="stat"),
            panel(13, "Seconds since last success", "time() - max by (gate) (max_over_time(airlock_gate_last_success_ts[7d]))", ds_uid, 18, 0, w=6, h=6, unit="s", kind="stat"),
            panel(1, "Gate runs (per 5 min)", "sum by (gate) (sum_over_time(airlock_gate_runs_total[5m]))", ds_uid, 0, 6),
            panel(2, "Gate errors (per 5 min)", "sum by (gate) (sum_over_time(airlock_gate_errors_total[5m]))", ds_uid, 12, 6),
            panel(3, "Gate latency (ms, last sample per 5 min)", "max by (gate) (max_over_time(airlock_gate_elapsed_ms[5m]))", ds_uid, 0, 14, unit="ms"),
            panel(4, "Blocks per gate (per 5 min)", "sum by (gate) (sum_over_time(airlock_gate_blocks_total[5m]))", ds_uid, 12, 14),
        ],
    }


def main() -> None:
    c = _client()
    ds_uid = prometheus_uid(c)
    r = c.post("/api/dashboards/db", json={"dashboard": dashboard(ds_uid), "overwrite": True, "message": "airlock bootstrap"})
    r.raise_for_status()
    body = r.json()
    base = os.environ["GRAFANA_URL"].rstrip("/")
    print(json.dumps({"prometheus_uid": ds_uid, "dashboard_uid": body.get("uid"), "dashboard_url": base + body.get("url", ""), "version": body.get("version")}))


if __name__ == "__main__":
    main()
