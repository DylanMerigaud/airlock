"""The alert rules the bootstrap provisions: three rules on the pushed counters, threshold > 0, no data is OK. No cloud call."""

from __future__ import annotations

import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("grafana_bootstrap", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "grafana_bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def test_three_rules_with_stable_uids_on_the_pushed_counters():
    rules = bootstrap.alert_rules("grafanacloud-prom")
    assert [r["uid"] for r in rules] == ["airlock-daily-proof-failed", "airlock-gate-errors", "airlock-calibration-missed"]
    assert [r["title"] for r in rules] == ["Airlock daily proof failed", "Airlock gate errors", "Airlock calibration missed"]
    exprs = [r["data"][0]["model"]["expr"] for r in rules]
    assert exprs == [
        'sum(sum_over_time(airlock_daily_proof_total{outcome="fail"}[13h]))',
        "sum by (gate) (sum_over_time(airlock_gate_errors_total[15m]))",
        "sum by (gate) (sum_over_time(airlock_calibration_misses_total[24h]))",
    ]


def test_each_rule_fires_on_a_positive_value_and_reads_no_data_as_ok():
    for rule in bootstrap.alert_rules("grafanacloud-prom"):
        assert rule["folderUID"] == bootstrap.FOLDER_UID and rule["ruleGroup"] == bootstrap.RULE_GROUP
        assert rule["condition"] == "C" and rule["for"] == "0s"
        assert rule["noDataState"] == "OK" and rule["execErrState"] == "Error"
        query, threshold = rule["data"]
        assert query["datasourceUid"] == "grafanacloud-prom" and query["model"]["instant"] is True
        assert threshold["datasourceUid"] == "__expr__" and threshold["model"]["type"] == "threshold" and threshold["model"]["expression"] == "A"
        assert threshold["model"]["conditions"][0]["evaluator"] == {"type": "gt", "params": [0]}
        assert rule["labels"] == {"app": "airlock", "owner": "platform"}
        assert rule["annotations"]["summary"]


def test_contact_point_and_policy_names_agree():
    assert bootstrap.CONTACT_POINT == "airlock-email"
    assert bootstrap.DEFAULT_ALERT_EMAIL == "dylanmerigaud@gmail.com"
    assert bootstrap.PROVISIONING_HEADERS == {"X-Disable-Provenance": "true"}
