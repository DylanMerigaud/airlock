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
        'sum(sum_over_time(airlock_daily_proof_total{outcome="fail"}[13h]))',
        "sum by (gate) (sum_over_time(airlock_gate_errors_total[15m]))",
        "sum by (gate) (sum_over_time(airlock_calibration_misses_total[24h]))",
        'sum(sum_over_time(airlock_verdict_total{status="ERROR"}[15m]))',
        "sum(sum_over_time(airlock_daily_proof_total[13h]))",
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
