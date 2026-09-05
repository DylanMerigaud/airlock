"""airlock.tracing: the exporter is installed once and only with a token, a gate runs in its own span, the Loki
body carries the trace id, the Explore URL opens the trace. No network: an in-memory exporter stands for the gateway."""

from __future__ import annotations

import base64
import json
import logging
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from airlock import tracing
from airlock.gates.base import Asset, GateResult, loki_event, run_gate

RUN = "e-0123456789abcdef"
TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"


def test_configure_without_a_token_exports_nothing_and_says_so(monkeypatch, caplog):
    tracing._reset_for_tests()
    monkeypatch.delenv("GRAFANA_OTLP_TOKEN", raising=False)
    monkeypatch.delenv("GRAFANA_OTLP_URL", raising=False)
    with caplog.at_level(logging.WARNING, logger="airlock.tracing"):
        assert tracing.configure() is False
    assert "GRAFANA_OTLP_TOKEN not set" in caplog.text
    assert tracing.exporting() is False and tracing.force_flush() is True
    tracing._reset_for_tests()


def test_an_empty_url_turns_tracing_off_on_purpose(monkeypatch, caplog):
    tracing._reset_for_tests()
    monkeypatch.setenv("GRAFANA_OTLP_URL", "")
    monkeypatch.setenv("GRAFANA_OTLP_TOKEN", "t")
    with caplog.at_level(logging.INFO, logger="airlock.tracing"):
        assert tracing.configure() is False
    assert "tracing off" in caplog.text
    tracing._reset_for_tests()


def test_the_exporter_posts_to_the_gateway_with_basic_auth():
    assert tracing.basic_auth("1811382", "tok") == "Basic " + base64.b64encode(b"1811382:tok").decode()
    exporter = tracing.otlp_exporter("https://otlp.example/otlp/v1/traces", "1811382", "tok")
    assert exporter._endpoint == "https://otlp.example/otlp/v1/traces"  # pyright: ignore[reportAttributeAccessIssue]
    assert exporter._headers["Authorization"] == tracing.basic_auth("1811382", "tok")  # pyright: ignore[reportAttributeAccessIssue]


def test_explore_url_opens_the_trace_in_the_tempo_datasource(monkeypatch):
    monkeypatch.delenv("GRAFANA_TEMPO_UID", raising=False)
    url = tracing.explore_url(TRACE, base="https://stack.grafana.net/")
    parsed = urlparse(url)
    assert url.startswith("https://stack.grafana.net/explore?schemaVersion=1&panes=")
    q = parse_qs(parsed.query)
    panes = json.loads(q["panes"][0])
    query = panes["a"]["queries"][0]
    assert panes["a"]["datasource"] == "grafanacloud-traces" and query["datasource"]["uid"] == "grafanacloud-traces"
    assert query["queryType"] == "traceql" and query["query"] == TRACE
    assert q["orgId"] == ["1"]
    assert tracing.explore_url(TRACE, base="https://x", datasource_uid="my-tempo").count("my-tempo") == 2


def test_current_trace_id_is_none_outside_a_span():
    assert tracing.current_trace_id() is None


def test_flush_on_root_end_flushes_root_spans_only():
    class FakeBatch:
        flushed = 0

        def force_flush(self, timeout_millis):
            self.flushed += 1
            return True

    batch = FakeBatch()
    flusher = tracing.FlushOnRootEnd(batch)  # pyright: ignore[reportArgumentType]
    flusher.on_end(SimpleNamespace(parent=SimpleNamespace(span_id=1)))  # pyright: ignore[reportArgumentType]
    assert batch.flushed == 0
    flusher.on_end(SimpleNamespace(parent=None))  # pyright: ignore[reportArgumentType]
    assert batch.flushed == 1 and flusher.flushes == 1


@pytest.fixture(scope="module")
def exporter() -> InMemorySpanExporter:
    """The one provider of the test process, with an in-memory exporter in place of the gateway. The OTel API
    lets a process set its global provider once, so every test below shares it."""
    mem = InMemorySpanExporter()
    tracing._reset_for_tests()
    assert tracing.configure(mem) is True
    assert isinstance(trace.get_tracer_provider(), TracerProvider)
    assert tracing.configure() is True  # the second call returns the first decision, whatever the env
    return mem


def test_a_span_of_our_own_carries_prefixed_attributes_and_a_trace_id(exporter: InMemorySpanExporter):
    exporter.clear()
    with tracing.span("airlock.gate.rights", gate="rights", run_id=RUN, asset_id="clip", fault=None, cost_usd=0.25, ok=True) as s:
        inside = tracing.current_trace_id()
        assert inside is not None and len(inside) == 32 and int(inside, 16) > 0
        assert tracing.trace_id_of(s) == inside
    spans = exporter.get_finished_spans()  # the root span ended: the flusher exported the batch
    assert [x.name for x in spans] == ["airlock.gate.rights"]
    attrs = dict(spans[0].attributes or {})
    assert attrs == {"airlock.gate": "rights", "airlock.run_id": RUN, "airlock.asset_id": "clip", "airlock.cost_usd": 0.25, "airlock.ok": True}
    assert format(spans[0].context.trace_id, "032x") == inside


def test_run_gate_opens_the_gate_span_and_the_loki_body_carries_its_trace_id(exporter: InMemorySpanExporter):
    exporter.clear()
    events = []

    class FakeLoki:
        def push_event(self, labels, event):
            events.append((labels, event))
            return 204

    asset = Asset(asset_id="nimbus-clean-clip", path="", gcs_uri="gs://b/nimbus-clean-clip.mp4", run_id=RUN)
    result = run_gate("rights", lambda a: GateResult(gate="rights", status="PASS", reasons=["fine"]), asset, "source", mute=False, loki=FakeLoki())  # pyright: ignore[reportArgumentType]
    assert result.status == "PASS"
    spans = exporter.get_finished_spans()
    assert len(spans) == 1 and spans[0].name == "airlock.gate.rights"
    attrs = dict(spans[0].attributes or {})
    assert attrs["airlock.status"] == "PASS" and attrs["airlock.run_id"] == RUN and isinstance(attrs["airlock.elapsed_ms"], int)
    assert attrs["airlock.telemetry_muted"] is False and "airlock.fault" not in attrs
    assert spans[0].status.status_code == StatusCode.UNSET
    labels, body = events[0]
    assert body["trace_id"] == format(spans[0].context.trace_id, "032x") and body["run_id"] == RUN
    assert labels == {"gate": "rights", "status": "PASS", "runtime": "local"} or labels["gate"] == "rights"


def test_a_gate_error_marks_the_span(exporter: InMemorySpanExporter):
    exporter.clear()
    asset = Asset(asset_id="clip", path="", run_id=RUN)
    result = run_gate("claim", lambda a: GateResult(gate="claim", status="PASS"), asset, "source", mute=True, fault="timeout")
    assert result.status == "ERROR"
    span = exporter.get_finished_spans()[0]
    assert span.status.status_code == StatusCode.ERROR and "TimeoutError" in (span.status.description or "")
    attrs = dict(span.attributes or {})
    assert attrs["airlock.fault"] == "timeout" and attrs["airlock.status"] == "ERROR" and attrs["airlock.telemetry_muted"] is True


def test_loki_event_without_a_span_has_no_trace_id(exporter: InMemorySpanExporter):
    del exporter
    body = loki_event(Asset(asset_id="clip", path="", run_id=RUN), GateResult(gate="rights", status="PASS"))
    assert "trace_id" not in body
