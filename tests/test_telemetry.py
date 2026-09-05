import pytest

from airlock import telemetry
from airlock.telemetry import line


def test_line_formats_tags_and_int_fields():
    out = line("airlock_gate", {"gate": "rights"}, {"runs_total": 1, "elapsed_ms": 240}, ts_ns=1700000000000000000)
    assert out == "airlock_gate,gate=rights elapsed_ms=240i,runs_total=1i 1700000000000000000"


def test_line_escapes_tag_values():
    out = line("m", {"gate": "a b,c=d"}, {"v": 1.5}, ts_ns=1)
    assert out == "m,gate=a\\ b\\,c\\=d v=1.5 1"


def test_line_rejects_empty_fields():
    with pytest.raises(ValueError):
        line("m", {}, {}, ts_ns=1)


@pytest.fixture
def fresh_pushers():
    """Every test starts and ends with no shared pusher, whatever another test left behind."""
    telemetry.close_shared_pushers()
    yield
    telemetry.close_shared_pushers()


def test_shared_pushers_are_built_once_and_closed_at_reset(monkeypatch, fresh_pushers):
    """One Influx client and one Loki client per process: the second call returns the same objects,
    close_shared_pushers() closes them, the next call rebuilds from the environment."""
    monkeypatch.setenv("GRAFANA_INFLUX_URL", "https://influx.example/write")
    monkeypatch.setenv("GRAFANA_INFLUX_USER", "1")
    monkeypatch.setenv("GRAFANA_INFLUX_TOKEN", "t")
    monkeypatch.setenv("GRAFANA_LOKI_URL", "https://loki.example")
    monkeypatch.setenv("GRAFANA_LOKI_USER", "2")
    monkeypatch.setenv("GRAFANA_LOKI_TOKEN", "t")
    influx, loki = telemetry.shared_pushers()
    assert influx is not None and loki is not None
    assert telemetry.shared_pushers() == (influx, loki)
    assert loki.url == "https://loki.example/loki/api/v1/push"
    telemetry.close_shared_pushers()
    assert influx.client.is_closed and loki.client.is_closed
    rebuilt = telemetry.shared_pushers()
    assert rebuilt[0] is not influx and rebuilt[1] is not loki


def test_shared_pushers_are_none_when_the_env_is_absent(monkeypatch, fresh_pushers):
    for name in ("GRAFANA_INFLUX_URL", "GRAFANA_LOKI_URL"):
        monkeypatch.delenv(name, raising=False)
    assert telemetry.shared_pushers() == (None, None)


def test_half_a_configuration_raises_and_names_the_missing_variables(monkeypatch, fresh_pushers):
    monkeypatch.setenv("GRAFANA_INFLUX_URL", "https://influx.example/write")
    monkeypatch.delenv("GRAFANA_INFLUX_USER", raising=False)
    monkeypatch.delenv("GRAFANA_INFLUX_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="GRAFANA_INFLUX_USER, GRAFANA_INFLUX_TOKEN"):
        telemetry.shared_pushers()


def test_run_gate_uses_the_pushers_it_is_given(monkeypatch):
    """A test's own pushers stand in for the shared pair, so what a gate run pushes can be read back."""
    from airlock.gates.base import Asset, GateResult, run_gate

    class FakeInflux:
        lines: list[str] = []

        def push_lines(self, lines):
            self.lines.extend(lines)
            return 204

    class FakeLoki:
        events: list[tuple[dict, dict]] = []

        def push_event(self, labels, event):
            self.events.append((labels, event))
            return 204

    monkeypatch.setenv("AIRLOCK_RUNTIME", "test")
    influx, loki = FakeInflux(), FakeLoki()
    asset = Asset(asset_id="a", path="", gcs_uri="gs://b/a.mp4", run_id="e-1")
    r = run_gate("brand", lambda a: GateResult(gate="brand", status="PASS"), asset, "charter", mute=False, influx=influx, loki=loki)  # type: ignore[arg-type]
    assert r.status == "PASS"
    assert len(influx.lines) == 1 and influx.lines[0].startswith("airlock_gate,gate=brand ") and "runs_total=1i" in influx.lines[0]
    assert loki.events[0][0] == {"gate": "brand", "status": "PASS", "runtime": "test"}
    assert loki.events[0][1]["run_id"] == "e-1"


def test_loki_lines_are_compact_so_the_stack_default_derived_field_links_them():
    import re

    text = telemetry.loki_line({"asset_id": "clip", "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736", "status": "PASS", "elapsed_ms": 12})
    assert '"trace_id":"4bf92f3577b34da6a3ce929d0e0e4736"' in text and ": " not in text
    stack_default = re.compile(r'[tT]race_?[iI][dD]"?[:=]"?(\w+)')  # the regex of the traceID derived field Grafana Cloud provisions
    m = stack_default.search(text)
    assert m is not None and m.group(1) == "4bf92f3577b34da6a3ce929d0e0e4736"
