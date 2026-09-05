"""The envelope around a gate: the run id in every Loki event, the injected fault, the datasource pins."""

import pytest

from airlock.gates.base import FAULT_TIMEOUT, Asset, GateResult, inject_fault, loki_event, run_gate
from airlock.grafana_mcp import pick_datasource_uid, pinned_loki_uid, pinned_prometheus_uid

RUN = "e-0123456789abcdef"


def asset() -> Asset:
    return Asset(asset_id="nimbus-clean-clip", path="", gcs_uri="gs://b/nimbus-clean-clip.mp4", run_id=RUN)


def passing(a: Asset) -> GateResult:
    return GateResult(gate="rights", status="PASS", reasons=["fine"])


def test_loki_event_carries_the_asset_and_the_run():
    body = loki_event(asset(), GateResult(gate="rights", status="PASS", reasons=["fine"]))
    assert body["asset_id"] == "nimbus-clean-clip" and body["run_id"] == RUN and body["status"] == "PASS"
    assert "fault" not in body


def test_loki_event_names_the_injected_fault():
    body = loki_event(asset(), GateResult(gate="rights", status="ERROR"), fault=FAULT_TIMEOUT)
    assert body["fault"] == "timeout"


def test_run_gate_without_telemetry_env_still_returns(monkeypatch):
    monkeypatch.delenv("GRAFANA_INFLUX_URL", raising=False)
    monkeypatch.delenv("GRAFANA_LOKI_URL", raising=False)
    r = run_gate("rights", passing, asset(), "source", mute=True)
    assert r.status == "PASS" and r.gate == "rights" and r.source_of_truth == "source"


def test_injected_timeout_becomes_error_with_the_message_and_spends_nothing(monkeypatch):
    calls = []

    def spending_gate(a: Asset) -> GateResult:
        calls.append(a)
        return GateResult(gate="rights", status="PASS")

    r = run_gate("rights", spending_gate, asset(), "source", mute=True, fault=FAULT_TIMEOUT)
    assert calls == []
    assert r.status == "ERROR"
    assert r.reasons == [f"TimeoutError: Video Intelligence operation timed out after 1 s (fault injected for run {RUN})"]
    assert "TimeoutError" in r.evidence[0]["traceback"]
    assert r.usage.get("cost_usd") in (None, 0, 0.0)


def test_unknown_fault_kind_is_an_error_too():
    with pytest.raises(ValueError, match="unknown fault 'crash'"):
        inject_fault("crash", "rights", RUN)
    r = run_gate("rights", passing, asset(), "source", mute=True, fault="crash")
    assert r.status == "ERROR" and r.reasons[0].startswith("ValueError: unknown fault 'crash'")


def test_datasource_uids_are_pinned_from_env(monkeypatch):
    monkeypatch.delenv("GRAFANA_PROM_UID", raising=False)
    monkeypatch.delenv("GRAFANA_LOKI_UID", raising=False)
    assert pinned_prometheus_uid() == "grafanacloud-prom" and pinned_loki_uid() == "grafanacloud-logs"
    monkeypatch.setenv("GRAFANA_LOKI_UID", "loki-x")
    monkeypatch.setenv("GRAFANA_PROM_UID", "")
    assert pinned_loki_uid() == "loki-x" and pinned_prometheus_uid() == ""


def test_pick_datasource_by_type_is_first_of_type():
    text = ('[{"uid": "grafanacloud-alert-state-history", "type": "loki"}, {"uid": "grafanacloud-logs", "type": "loki"}, '
            '{"uid": "grafanacloud-prom", "type": "prometheus"}]')
    assert pick_datasource_uid(text, "prometheus") == "grafanacloud-prom"
    assert pick_datasource_uid(text, "loki") == "grafanacloud-alert-state-history"  # why the uid is pinned, not picked
    with pytest.raises(LookupError):
        pick_datasource_uid(text, "tempo")


def test_a_failing_telemetry_push_never_takes_the_run_down():
    """A telemetry endpoint answering 503 is recorded on the result; the gate's answer stands, and the
    verdict finds no Loki event for the run, which is R1 by construction (second panel, 2026-09-05)."""

    class Refuses:
        def push_lines(self, lines):
            raise RuntimeError("influx push failed: HTTP 503 Loading")

    sent: list = []

    class Records:
        def push_event(self, labels, event):
            sent.append((labels, event))

    r = run_gate("provenance", lambda a: GateResult(gate="provenance", status="PASS", reasons=["ok"]), asset(), "c2pa",
                 influx=Refuses(), loki=Records())
    assert r.status == "PASS"
    assert any("influx: RuntimeError" in str(e.get("telemetry_error")) for e in r.evidence)
    assert len(sent) == 1 and sent[0][1]["run_id"] == RUN  # the Loki event still went out after the Influx failure
