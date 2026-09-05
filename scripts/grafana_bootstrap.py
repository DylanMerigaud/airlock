"""Create the "Airlock gates" dashboard, the Airlock alert rules and their contact point on the Grafana
stack, and print the Prometheus datasource uid.

Uses the Grafana HTTP API with the service account token (Editor). Idempotent: the dashboard is
upserted by uid, the folder by title, the contact point by name, the alert rules by uid through the
provisioning API (/api/v1/provisioning), the notification policy tree is replaced whole.

Three rules, all on the counters the gates and the proof push (a series is absent when nothing
happened, so "no data" is OK, not an alert):
  Airlock daily proof failed    sum(sum_over_time(airlock_daily_proof_total{outcome="fail"}[13h])) > 0
  Airlock gate errors           sum by (gate) (sum_over_time(airlock_gate_errors_total[15m])) > 0
  Airlock calibration missed    sum by (gate) (sum_over_time(airlock_calibration_misses_total[24h])) > 0
One contact point (email, AIRLOCK_ALERT_EMAIL, default dylanmerigaud@gmail.com), the default policy
routed to it. The investigator agent reads the rules' state through mcp-grafana's list_alert_rules.

Logs to traces: the Loki datasource needs a derived field that turns the trace_id of an Airlock line into a
link to the Tempo datasource. Grafana Cloud provisions its Loki datasource read-only (PUT answers 403) with
such a field already (traceID, regex [tT]race_?[iI][dD]"?[:=]"?(\\w+)); the bootstrap checks that one of the
datasource's fields matches an Airlock line and points at Tempo, adds ours when the datasource is writable
and none does, and says so when it is read-only. Verified by GET either way.

Environment: GRAFANA_URL, GRAFANA_SERVICE_ACCOUNT_TOKEN, optional AIRLOCK_ALERT_EMAIL, GRAFANA_LOKI_UID,
GRAFANA_TEMPO_UID.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

import httpx

DASHBOARD_UID = "airlock-gates"
GATES = ["rights", "claim", "brand", "provenance", "verdict", "spike"]
LOKI_UID = os.environ.get("GRAFANA_LOKI_UID", "grafanacloud-logs")
TEMPO_UID = os.environ.get("GRAFANA_TEMPO_UID", "grafanacloud-traces")
# What airlock.telemetry.loki_line writes (compact JSON): the field must match this.
SAMPLE_LOKI_LINE = '{"asset_id":"clip","run_id":"e-1","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","gate":"rights","status":"PASS"}'
SAMPLE_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
TRACE_FIELD = {"name": "trace_id", "matcherType": "regex", "matcherRegex": '"trace_id":"(\\w+)"', "url": "${__value.raw}", "datasourceUid": TEMPO_UID}


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


GATE = 'gate!="spike"'  # the M1 spike series stays in Grafana as history, out of the gate panels


def panel(pid: int, title: str, expr: str, ds_uid: str, x: int, y: int, w: int = 12, h: int = 8, unit: str = "short", kind: str = "timeseries",
          legend: str = "{{gate}}", thresholds: list | None = None, overrides: list | None = None) -> dict:
    defaults: dict = {"unit": unit}
    if thresholds:
        defaults["thresholds"] = {"mode": "absolute", "steps": thresholds}
        defaults["color"] = {"mode": "thresholds"}
    return {
        "id": pid,
        "type": kind,
        "title": title,
        "datasource": {"type": "prometheus", "uid": ds_uid},
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
        # A stat tile reduces "last not null" over a range query, which keeps a series alive for the width of
        # the range after its last sample: a 7 d tile counting day 8 (second panel, 2026-09-05). Stat tiles
        # query the instant value; time series keep the range.
        "targets": [{"refId": "A", "expr": expr, "legendFormat": legend, "datasource": {"type": "prometheus", "uid": ds_uid},
                     **({"instant": True, "range": False} if kind == "stat" else {})}],
    }


def by_name_thresholds(name: str, steps: list) -> dict:
    """A field override on a stat panel: the series whose display name is `name` gets its own thresholds."""
    return {"matcher": {"id": "byName", "options": name},
            "properties": [{"id": "thresholds", "value": {"mode": "absolute", "steps": steps}}, {"id": "color", "value": {"mode": "thresholds"}}]}


def dashboard(ds_uid: str) -> dict:
    return {
        "uid": DASHBOARD_UID,
        "title": "Airlock gates",
        "tags": ["airlock"],
        "timezone": "browser",
        "schemaVersion": 39,
        "time": {"from": "now-7d", "to": "now"},
        "refresh": "1m",
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
            panel(11, "Calibration catches (7d)", f"sum by (gate) (sum_over_time(airlock_calibration_catches_total{{{GATE}}}[7d]))", ds_uid, 6, 0, w=6, h=6, kind="stat",
                  thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 1}]),
            panel(12, "Calibration misses (7d)", f"sum by (gate) (sum_over_time(airlock_calibration_misses_total{{{GATE}}}[7d]))", ds_uid, 12, 0, w=6, h=6, kind="stat",
                  thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 1}]),
            panel(14, "Cost per check, list price USD (7d)", "sum(sum_over_time(airlock_verdict_cost_usd[7d])) / clamp_min(sum(sum_over_time(airlock_verdict_total[7d])), 1)", ds_uid, 0, 22, w=6, h=6, kind="stat", unit="currencyUSD", legend="per check"),
            panel(15, "Cost per gate run, list price USD (per 5 min)", f"sum by (gate) (sum_over_time(airlock_gate_cost_usd{{{GATE}}}[5m]))", ds_uid, 6, 22, w=18, h=6, unit="currencyUSD"),
            # pass: red at 0, green from 1; fail: the opposite, so a failed proof never paints green (it did until 2026-09-05)
            panel(16, "Daily proofs (7d): every gate re-proven, then a clean PASS", "sum by (outcome) (sum_over_time(airlock_daily_proof_total[7d]))", ds_uid, 0, 28, w=6, h=6, kind="stat", legend="{{outcome}}",
                  thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 1}],
                  overrides=[by_name_thresholds("fail", [{"color": "green", "value": None}, {"color": "red", "value": 1}])]),
            panel(17, "Cost per daily proof, list price USD (7d)", "sum(sum_over_time(airlock_daily_proof_cost_usd[7d])) / clamp_min(sum(sum_over_time(airlock_daily_proof_total[7d])), 1)", ds_uid, 6, 28, w=6, h=6, kind="stat", unit="currencyUSD", legend="per proof"),
            panel(18, "Daily proofs over time (per 12 h)", "sum by (outcome) (sum_over_time(airlock_daily_proof_total[12h]))", ds_uid, 12, 28, w=12, h=6, legend="{{outcome}}"),
            panel(13, "Seconds since last success (stale past 900 s)", f"time() - max by (gate) (max_over_time(airlock_gate_last_success_ts{{{GATE}}}[7d]))", ds_uid, 18, 0, w=6, h=6, unit="s", kind="stat",
                  thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 900}]),
            panel(1, "Gate runs (per 5 min)", f"sum by (gate) (sum_over_time(airlock_gate_runs_total{{{GATE}}}[5m]))", ds_uid, 0, 6),
            panel(2, "Gate errors (per 5 min)", f"sum by (gate) (sum_over_time(airlock_gate_errors_total{{{GATE}}}[5m]))", ds_uid, 12, 6),
            panel(3, "Gate latency (ms, last sample per 5 min)", f"max by (gate) (max_over_time(airlock_gate_elapsed_ms{{{GATE}}}[5m]))", ds_uid, 0, 14, unit="ms"),
            panel(4, "Blocks per gate (per 5 min)", f"sum by (gate) (sum_over_time(airlock_gate_blocks_total{{{GATE}}}[5m]))", ds_uid, 12, 14),
        ],
    }


FOLDER_TITLE = "Airlock"
FOLDER_UID = "airlock"
RULE_GROUP = "airlock"
RULE_GROUP_INTERVAL_S = 60
CONTACT_POINT = "airlock-email"
DEFAULT_ALERT_EMAIL = "dylanmerigaud@gmail.com"
# X-Disable-Provenance: the objects stay editable in the Grafana UI (a provisioned object is read-only there).
PROVISIONING_HEADERS = {"X-Disable-Provenance": "true"}


def alert_rules(ds_uid: str) -> list[dict]:
    """The Airlock alert rules, keyed by a stable uid. Each is one instant PromQL query (A) and one
    threshold expression (C: A > 0); the rule fires at the next evaluation (for: 0s), and a missing series
    reads as OK because these counters only exist when a failure was pushed."""
    specs = [
        ("airlock-daily-proof-failed", "Airlock daily proof failed",
         'sum(sum_over_time(airlock_daily_proof_total{outcome="fail"}[13h]))',
         "A scheduled proof failed in the last 13 hours: a gate missed its injected defect, or the clean clip did not PASS. Read the proof's Loki lines ({app=\"airlock\"} |= \"daily-proof\")."),
        ("airlock-gate-errors", "Airlock gate errors",
         "sum by (gate) (sum_over_time(airlock_gate_errors_total[15m]))",
         "A gate raised in the last 15 minutes (its run is ERROR and the verdict on that run is BLOCK control unavailable). Read the gate's Loki lines ({app=\"airlock\", gate=\"<gate>\", status=\"ERROR\"})."),
        ("airlock-calibration-missed", "Airlock calibration missed",
         "sum by (gate) (sum_over_time(airlock_calibration_misses_total[24h]))",
         "A calibration run in the last 24 hours injected a defect the gate did not catch: the gate's PASS is advisory until the next catch (rule R2)."),
        ("airlock-instrument-error", "Airlock verdict could not reach Grafana",
         'sum(sum_over_time(airlock_verdict_total{status="ERROR"}[15m]))',
         "A verdict ended in an instrument error in the last 15 minutes: the verdict agent could not complete its Grafana questions (a paused stack past the 180 s wake budget, or an MCP failure). The run has no verdict and a human must look."),
    ]
    rules = []
    for uid, title, expr, summary in specs:
        rules.append({
            "uid": uid,
            "title": title,
            "ruleGroup": RULE_GROUP,
            "folderUID": FOLDER_UID,
            "condition": "C",
            "for": "0s",
            "noDataState": "OK",
            "execErrState": "Error",
            "orgID": 1,
            "annotations": {"summary": summary, "expr": expr},
            "labels": {"app": "airlock", "owner": "platform"},
            "data": [
                {"refId": "A", "relativeTimeRange": {"from": 600, "to": 0}, "datasourceUid": ds_uid,
                 "model": {"refId": "A", "expr": expr, "instant": True, "range": False, "intervalMs": 1000, "maxDataPoints": 43200}},
                {"refId": "C", "relativeTimeRange": {"from": 0, "to": 0}, "datasourceUid": "__expr__",
                 "model": {"refId": "C", "type": "threshold", "expression": "A",
                           "conditions": [{"evaluator": {"type": "gt", "params": [0]}, "operator": {"type": "and"}, "query": {"params": ["C"]}, "reducer": {"type": "last", "params": []}, "type": "query"}]}},
            ],
        })
    # The dead man's switch: the proof runs every 6 hours and pushes one sample; thirteen hours without one is
    # an outage of the schedule itself (Scheduler, the job, a quota), which no ">" rule on a counter can see.
    # No data is the alert here, so noDataState is Alerting.
    rules.append({
        "uid": "airlock-daily-proof-missing",
        "title": "Airlock daily proof did not run",
        "ruleGroup": RULE_GROUP,
        "folderUID": FOLDER_UID,
        "condition": "C",
        "for": "0s",
        "noDataState": "Alerting",
        "execErrState": "Error",
        "orgID": 1,
        "annotations": {"summary": "No daily proof sample in the last 13 hours: the schedule, the job or its quota failed. Check the Cloud Run job executions.",
                        "expr": "sum(sum_over_time(airlock_daily_proof_total[13h]))"},
        "labels": {"app": "airlock", "owner": "platform"},
        "data": [
            {"refId": "A", "relativeTimeRange": {"from": 600, "to": 0}, "datasourceUid": ds_uid,
             "model": {"refId": "A", "expr": "sum(sum_over_time(airlock_daily_proof_total[13h]))", "instant": True, "range": False,
                       "intervalMs": 1000, "maxDataPoints": 43200}},
            {"refId": "C", "relativeTimeRange": {"from": 0, "to": 0}, "datasourceUid": "__expr__",
             "model": {"refId": "C", "type": "threshold", "expression": "A",
                       "conditions": [{"evaluator": {"type": "lt", "params": [1]}, "operator": {"type": "and"}, "query": {"params": ["C"]},
                                       "reducer": {"type": "last", "params": []}, "type": "query"}]}},
        ],
    })
    return rules


def ensure_folder(c: httpx.Client) -> str:
    """The "Airlock" folder the alert rules live in (alert rules need a folder), by uid."""
    r = c.get(f"/api/folders/{FOLDER_UID}")
    if r.status_code == 200:
        return r.json()["uid"]
    r = c.post("/api/folders", json={"uid": FOLDER_UID, "title": FOLDER_TITLE})
    r.raise_for_status()
    return r.json()["uid"]


def ensure_contact_point(c: httpx.Client, email: str) -> str:
    """One email contact point, upserted by name; returns its uid."""
    r = c.get("/api/v1/provisioning/contact-points", params={"name": CONTACT_POINT})
    r.raise_for_status()
    body = {"name": CONTACT_POINT, "type": "email", "settings": {"addresses": email, "singleEmail": True}, "disableResolveMessage": False}
    existing = [cp for cp in r.json() if cp.get("name") == CONTACT_POINT]
    if existing:
        uid = existing[0]["uid"]
        c.put(f"/api/v1/provisioning/contact-points/{uid}", json={**body, "uid": uid}, headers=PROVISIONING_HEADERS).raise_for_status()
        return uid
    r = c.post("/api/v1/provisioning/contact-points", json=body, headers=PROVISIONING_HEADERS)
    r.raise_for_status()
    return r.json()["uid"]


def ensure_policy(c: httpx.Client) -> dict:
    """The notification policy tree: everything to the Airlock contact point, grouped by folder and rule."""
    tree = {"receiver": CONTACT_POINT, "group_by": ["grafana_folder", "alertname"], "group_wait": "30s", "group_interval": "5m", "repeat_interval": "4h"}
    c.put("/api/v1/provisioning/policies", json=tree, headers=PROVISIONING_HEADERS).raise_for_status()
    return c.get("/api/v1/provisioning/policies").json()


def ensure_alert_rules(c: httpx.Client, ds_uid: str) -> list[dict]:
    """The rules, upserted by uid through the provisioning API; then the group's evaluation interval."""
    out = []
    for rule in alert_rules(ds_uid):
        r = c.get(f"/api/v1/provisioning/alert-rules/{rule['uid']}")
        if r.status_code == 200:
            r = c.put(f"/api/v1/provisioning/alert-rules/{rule['uid']}", json=rule, headers=PROVISIONING_HEADERS)
        else:
            r = c.post("/api/v1/provisioning/alert-rules", json=rule, headers=PROVISIONING_HEADERS)
        r.raise_for_status()
        saved = r.json()
        out.append({"uid": saved.get("uid"), "title": saved.get("title"), "folderUID": saved.get("folderUID"), "ruleGroup": saved.get("ruleGroup")})
    r = c.get(f"/api/v1/provisioning/folder/{FOLDER_UID}/rule-groups/{RULE_GROUP}")
    r.raise_for_status()
    group = r.json()
    if group.get("interval") != RULE_GROUP_INTERVAL_S:
        group["interval"] = RULE_GROUP_INTERVAL_S
        c.put(f"/api/v1/provisioning/folder/{FOLDER_UID}/rule-groups/{RULE_GROUP}", json=group, headers=PROVISIONING_HEADERS).raise_for_status()
    return out


def main() -> None:
    c = _client()
    ds_uid = prometheus_uid(c)
    r = c.post("/api/dashboards/db", json={"dashboard": dashboard(ds_uid), "overwrite": True, "message": "airlock bootstrap"})
    r.raise_for_status()
    body = r.json()
    base = os.environ["GRAFANA_URL"].rstrip("/")
    folder_uid = ensure_folder(c)
    contact_uid = ensure_contact_point(c, os.environ.get("AIRLOCK_ALERT_EMAIL", DEFAULT_ALERT_EMAIL))
    policy = ensure_policy(c)
    rules = ensure_alert_rules(c, ds_uid)
    trace_link = ensure_trace_link(c)
    print(json.dumps({"prometheus_uid": ds_uid, "dashboard_uid": body.get("uid"), "dashboard_url": base + body.get("url", ""), "version": body.get("version"),
                      "folder_uid": folder_uid, "contact_point": {"name": CONTACT_POINT, "uid": contact_uid}, "policy_receiver": policy.get("receiver"),
                      "alert_rules": rules, "rule_group_interval_s": RULE_GROUP_INTERVAL_S, "loki_trace_link": trace_link}))


def field_links_airlock_lines(field: dict[str, Any], tempo_uid: str = TEMPO_UID) -> bool:
    """True when this derived field points at the Tempo datasource and its regex pulls the trace id out of an Airlock line."""
    if field.get("datasourceUid") != tempo_uid or field.get("matcherType", "regex") != "regex":
        return False
    try:
        m = re.search(str(field.get("matcherRegex") or ""), SAMPLE_LOKI_LINE)
    except re.error:
        return False
    return bool(m and m.groups() and m.group(1) == SAMPLE_TRACE_ID)


def trace_link_plan(datasource: dict[str, Any], tempo_uid: str = TEMPO_UID) -> dict[str, Any]:
    """What to do about the Loki datasource's derived fields: nothing when one already links Airlock lines to Tempo, a PUT
    with ours added when the datasource is writable, a report when it is read-only (Grafana Cloud's provisioned one)."""
    fields = list((datasource.get("jsonData") or {}).get("derivedFields") or [])
    matching = [f.get("name") for f in fields if field_links_airlock_lines(f, tempo_uid)]
    if matching:
        return {"action": "none", "linked_by": matching, "read_only": bool(datasource.get("readOnly"))}
    if datasource.get("readOnly"):
        return {"action": "cannot", "linked_by": [], "read_only": True,
                "reason": "the Loki datasource is read-only and none of its derived fields links an Airlock line to Tempo"}
    return {"action": "put", "linked_by": [TRACE_FIELD["name"]], "read_only": False, "fields": fields + [{**TRACE_FIELD, "datasourceUid": tempo_uid}]}


def ensure_trace_link(c: httpx.Client, loki_uid: str = LOKI_UID, tempo_uid: str = TEMPO_UID) -> dict[str, Any]:
    """Logs to traces on the Loki datasource, idempotent, verified by GET. Never raises on a refusal: the answer says what stands."""
    r = c.get(f"/api/datasources/uid/{loki_uid}")
    r.raise_for_status()
    ds = r.json()
    plan = trace_link_plan(ds, tempo_uid)
    out: dict[str, Any] = {"loki_uid": loki_uid, "tempo_uid": tempo_uid, "action": plan["action"], "read_only": plan["read_only"]}
    if plan["action"] == "put":
        body = {k: ds[k] for k in ("name", "type", "url", "access", "basicAuth", "basicAuthUser", "isDefault") if k in ds}
        body["jsonData"] = {**(ds.get("jsonData") or {}), "derivedFields": plan["fields"]}
        put = c.put(f"/api/datasources/uid/{loki_uid}", json=body)
        out["put_status"] = put.status_code
        if put.status_code >= 300:
            out.update(action="cannot", reason=put.text[:200])
    elif plan["action"] == "cannot":
        out["reason"] = plan["reason"]
    after = c.get(f"/api/datasources/uid/{loki_uid}")
    after.raise_for_status()
    out["linked_by"] = trace_link_plan(after.json(), tempo_uid)["linked_by"]
    out["verified"] = bool(out["linked_by"])
    return out


if __name__ == "__main__":
    main()
