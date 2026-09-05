"""The alert rules the bootstrap provisions: four rules on the pushed counters (threshold > 0, no data is OK) and one dead man's
switch on the daily proof (no sample in 13 hours is the alert). No cloud call."""

from __future__ import annotations

import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("grafana_bootstrap", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "grafana_bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def test_five_rules_with_stable_uids_on_the_pushed_counters():
    rules = bootstrap.alert_rules("grafanacloud-prom")
    assert [r["uid"] for r in rules] == ["airlock-daily-proof-failed", "airlock-gate-errors", "airlock-calibration-missed",
                                         "airlock-instrument-error", "airlock-daily-proof-missing"]
    exprs = [r["data"][0]["model"]["expr"] for r in rules]
    assert exprs == [
        'sum(sum_over_time(airlock_daily_proof_total{outcome="fail"}[7h]))',
        "sum by (gate) (sum_over_time(airlock_gate_errors_total[15m]))",
        "sum by (gate) (sum_over_time(airlock_calibration_misses_total[24h]))",
        'sum(sum_over_time(airlock_verdict_total{status="ERROR"}[15m]))',
        "sum(sum_over_time(airlock_daily_proof_total[7h]))",
    ]


def test_counter_rules_fire_on_a_positive_value_and_read_no_data_as_ok():
    rules = bootstrap.alert_rules("grafanacloud-prom")
    for rule in rules[:4]:
        assert rule["folderUID"] == bootstrap.FOLDER_UID and rule["ruleGroup"] == bootstrap.RULE_GROUP
        assert rule["condition"] == "C" and rule["for"] == "0s"
        assert rule["noDataState"] == "OK" and rule["execErrState"] == "Error"
        query, threshold = rule["data"]
        assert query["datasourceUid"] == "grafanacloud-prom" and query["model"]["instant"] is True
        assert threshold["datasourceUid"] == "__expr__" and threshold["model"]["type"] == "threshold" and threshold["model"]["expression"] == "A"
        assert threshold["model"]["conditions"][0]["evaluator"] == {"type": "gt", "params": [0]}
        assert rule["labels"] == {"app": "airlock", "owner": "platform"}
        assert rule["annotations"]["summary"]


def test_the_dead_man_rule_alerts_on_no_data_and_on_less_than_one_proof():
    dead_man = bootstrap.alert_rules("grafanacloud-prom")[-1]
    assert dead_man["noDataState"] == "Alerting"
    assert dead_man["data"][1]["model"]["conditions"][0]["evaluator"] == {"type": "lt", "params": [1]}


def test_stat_tiles_query_the_instant_value_and_time_series_the_range():
    stat = bootstrap.panel(1, "t", "up", "ds", 0, 0, kind="stat")
    series = bootstrap.panel(2, "t", "up", "ds", 0, 0)
    assert stat["targets"][0]["instant"] is True and stat["targets"][0]["range"] is False
    assert "instant" not in series["targets"][0]


def test_contact_point_and_policy_names_agree():
    assert bootstrap.CONTACT_POINT == "airlock-email"
    assert bootstrap.DEFAULT_ALERT_EMAIL == "dylanmerigaud@gmail.com"
    assert bootstrap.PROVISIONING_HEADERS == {"X-Disable-Provenance": "true"}


# Logs to traces: the derived field on the Loki datasource. The two fields below are the ones Grafana Cloud provisions.
STACK_DEFAULT_FIELD = {"datasourceUid": "grafanacloud-traces", "matcherRegex": '[tT]race_?[iI][dD]"?[:=]"?(\\w+)', "matcherType": "regex",
                       "name": "traceID", "url": "${__value.raw}"}
STACK_LABEL_FIELD = {"datasourceUid": "grafanacloud-traces", "matcherRegex": "[tT]race_?[iI][dD]", "matcherType": "label", "name": "traceID (field)",
                     "url": "${__value.raw}"}


def test_the_stack_default_derived_field_links_a_compact_airlock_line():
    assert bootstrap.field_links_airlock_lines(STACK_DEFAULT_FIELD) is True
    assert bootstrap.field_links_airlock_lines(STACK_LABEL_FIELD) is False  # a label matcher, and the Airlock stream has no trace label
    assert bootstrap.field_links_airlock_lines({**STACK_DEFAULT_FIELD, "datasourceUid": "other-tempo"}) is False
    assert bootstrap.field_links_airlock_lines({**STACK_DEFAULT_FIELD, "matcherRegex": "("}) is False  # a broken regex is not a link
    assert bootstrap.field_links_airlock_lines(bootstrap.TRACE_FIELD) is True
    assert bootstrap.SAMPLE_LOKI_LINE.count('"trace_id":"') == 1  # the compact form airlock.telemetry.loki_line writes


def test_trace_link_plan_does_nothing_when_the_stack_links_already_and_reports_a_read_only_datasource():
    ds = {"uid": "grafanacloud-logs", "readOnly": True, "jsonData": {"derivedFields": [STACK_DEFAULT_FIELD, STACK_LABEL_FIELD], "timeout": "300"}}
    assert bootstrap.trace_link_plan(ds) == {"action": "none", "linked_by": ["traceID"], "read_only": True}
    bare = {"uid": "grafanacloud-logs", "readOnly": True, "jsonData": {"derivedFields": [STACK_LABEL_FIELD]}}
    plan = bootstrap.trace_link_plan(bare)
    assert plan["action"] == "cannot" and plan["linked_by"] == [] and "read-only" in plan["reason"]


def test_trace_link_plan_adds_our_field_to_a_writable_datasource_and_keeps_the_others():
    ds = {"uid": "loki", "readOnly": False, "jsonData": {"derivedFields": [STACK_LABEL_FIELD], "timeout": "300"}}
    plan = bootstrap.trace_link_plan(ds, tempo_uid="my-tempo")
    assert plan["action"] == "put" and plan["linked_by"] == ["trace_id"]
    assert plan["fields"][0] == STACK_LABEL_FIELD and plan["fields"][1]["datasourceUid"] == "my-tempo" and plan["fields"][1]["name"] == "trace_id"
    assert bootstrap.field_links_airlock_lines(plan["fields"][1], tempo_uid="my-tempo")
