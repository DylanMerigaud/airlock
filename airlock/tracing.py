"""One trace per run in Grafana Tempo; the trace id in every Loki line, the verdict and the incident.

ADK opens the spans of the run itself, through its tracer `gcp.vertex.agent`: the invocation, one
`invoke_agent <name>` per agent (the four gates, verdict, investigation, investigator, escalation),
`execute_tool <name>` and `generate_content <model>` around the investigator's calls. This module adds
what ADK does not do:

  - configure(): installs an OTLP/HTTP span exporter to the stack's gateway (GRAFANA_OTLP_URL, basic auth
    GRAFANA_OTLP_USER:GRAFANA_OTLP_TOKEN, airlock.settings.otlp()) on the global TracerProvider, once per
    process. When a provider exists already (`adk api_server`, which is what Agent Engine runs, builds one
    before the pipeline module loads) the exporter is added to it; otherwise one is created with the
    resource service.name=airlock, service.version (git, else "dev"), deployment.environment=AIRLOCK_RUNTIME.
    No token means no tracing, said once in the log.
  - span(name, **attributes): a span of Airlock's own around a gate (`airlock.gate.<name>`, in run_gate) or
    a Grafana call the verdict and the escalation make directly (`grafana.<tool>`), which no ADK span wraps.
  - current_trace_id() and explore_url(): the 32-hex id of the current trace, and the Grafana Explore URL
    that opens it in Tempo. Every Loki event body carries the id as trace_id (the Loki datasource's
    derived field turns it into a link, scripts/grafana_bootstrap.py), the verdict payload carries id and
    URL, the annotation says "trace <id>", the incident body has a "Trace:" line.

On Agent Engine the CPU is throttled the instant a request ends, so the batch exporter's thread may not
get to run between two requests: FlushOnRootEnd exports the batch when a root span ends, inside the
request that produced it (the pipeline's root span ends after the escalation, a gate's own span is the
root on the MCP server and in the calibration).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import pathlib
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import Span, StatusCode

from airlock import settings

log = logging.getLogger("airlock.tracing")

SERVICE_NAME = settings.OTEL_SERVICE_NAME
TRACER_NAME = "airlock"
ATTRIBUTE_PREFIX = "airlock."
EXPORT_TIMEOUT_S = 10.0
FLUSH_TIMEOUT_MS = 5000
# The Explore pane's range: a trace id lookup in Tempo is bounded by the pane's range (plus the datasource's
# time shift), and a week covers every run a reader would open from an incident or the console.
EXPLORE_RANGE = {"from": "now-7d", "to": "now"}
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

_lock = threading.Lock()
_state: dict[str, Any] = {"decided": False, "exporting": False, "processor": None}


def basic_auth(user: str, token: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()


def otlp_exporter(url: str, user: str, token: str) -> SpanExporter:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    return OTLPSpanExporter(endpoint=url, headers={"Authorization": basic_auth(user, token)}, timeout=EXPORT_TIMEOUT_S)


def service_version() -> str:
    """AIRLOCK_VERSION, else the short git sha of the checkout, else "dev" (a deployed image has no git)."""
    explicit = os.environ.get("AIRLOCK_VERSION", "")
    if explicit:
        return explicit
    try:
        out = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        return "dev"
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and sha else "dev"


def resource() -> Resource:
    """The resource of a provider this module creates. Resource.create merges the OTEL_* variables under these."""
    return Resource.create({"service.name": SERVICE_NAME, "service.version": service_version(), "deployment.environment": settings.runtime()})


class FlushOnRootEnd(SpanProcessor):
    """Exports the batch when a span with no parent ends: the run's spans leave with the request that made them."""

    def __init__(self, batch: BatchSpanProcessor) -> None:
        self.batch = batch
        self.flushes = 0

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        return None

    def on_end(self, span: ReadableSpan) -> None:
        if span.parent is not None:
            return
        self.flushes += 1
        try:
            self.batch.force_flush(FLUSH_TIMEOUT_MS)
        except Exception as exc:  # a flush that fails leaves the spans to the next one or to shutdown
            log.warning("trace flush failed: %s: %s", type(exc).__name__, exc)

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def configure(exporter: SpanExporter | None = None) -> bool:
    """Install the span exporter once per process; True when spans are exported.

    exporter: a test passes its own (an in-memory one); by default the OTLP/HTTP exporter to the gateway of
    airlock.settings.otlp(). Without GRAFANA_OTLP_TOKEN nothing is exported and the log says so once; a run
    still has a trace id wherever a TracerProvider exists (ADK's api server sets one). A second call returns
    the first decision.
    """
    with _lock:
        if _state["decided"]:
            return bool(_state["exporting"])
        _state["decided"] = True
        target = "the given exporter"
        if exporter is None:
            ep = settings.otlp()
            if not ep.url:
                log.info("GRAFANA_OTLP_URL is empty: tracing off")
                return False
            if ep.missing():
                log.warning("%s not set: traces are not exported", ", ".join(ep.missing()))
                return False
            exporter = otlp_exporter(ep.url, ep.user, ep.token)
            target = ep.url
        batch = BatchSpanProcessor(exporter, export_timeout_millis=int(EXPORT_TIMEOUT_S * 1000))
        provider = trace.get_tracer_provider()
        if isinstance(provider, TracerProvider):
            how = f"added to the existing TracerProvider (service.name={provider.resource.attributes.get('service.name')!r})"
        else:
            provider = TracerProvider(resource=resource())
            trace.set_tracer_provider(provider)
            if trace.get_tracer_provider() is not provider:  # the API refuses to replace a provider set elsewhere
                log.warning("tracing: the global TracerProvider is a %s, not an SDK provider; traces are not exported",
                            type(trace.get_tracer_provider()).__name__)
                return False
            how = "on a new TracerProvider"
        provider.add_span_processor(batch)
        provider.add_span_processor(FlushOnRootEnd(batch))
        _state.update(exporting=True, processor=batch)
        log.info("tracing: spans exported to %s, %s", target, how)
        return True


def exporting() -> bool:
    return bool(_state["exporting"])


def force_flush(timeout_ms: int = FLUSH_TIMEOUT_MS) -> bool:
    """Export what is queued now (the end of a local run); True when nothing is exported or the flush went through."""
    batch = _state["processor"]
    return True if batch is None else bool(batch.force_flush(timeout_ms))


def _reset_for_tests() -> None:
    _state.update(decided=False, exporting=False, processor=None)


def set_attributes(span: Span, **attributes: Any) -> None:
    """Attributes under the airlock. prefix; None is left out, anything not a number, a bool or a string is stringified."""
    for key, value in attributes.items():
        if value is None:
            continue
        span.set_attribute(ATTRIBUTE_PREFIX + key, value if isinstance(value, (bool, int, float, str)) else str(value))


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Span]:
    """A span of Airlock's own, child of the current one (an ADK agent span inside the pipeline, the root in a plain process)."""
    with trace.get_tracer(TRACER_NAME).start_as_current_span(name) as s:
        set_attributes(s, **attributes)
        yield s


def mark_error(span: Span, reason: str) -> None:
    span.set_status(StatusCode.ERROR, reason[:300])


def trace_id_of(span: Span) -> str | None:
    ctx = span.get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


def current_trace_id() -> str | None:
    """The 32-hex trace id of the current span, None outside a recording trace (no provider, or no span)."""
    return trace_id_of(trace.get_current_span())


def explore_url(trace_id: str, base: str | None = None, datasource_uid: str | None = None) -> str:
    """The Grafana Explore URL that opens this trace in the Tempo datasource (the panes form, schemaVersion 1)."""
    base = (base or settings.grafana_url()).rstrip("/")
    uid = datasource_uid or settings.tempo_uid()
    panes = {"a": {"datasource": uid,
                   "queries": [{"refId": "A", "datasource": {"type": "tempo", "uid": uid}, "queryType": "traceql", "query": trace_id}],
                   "range": EXPLORE_RANGE}}
    return f"{base}/explore?schemaVersion=1&panes={quote(json.dumps(panes, separators=(',', ':')), safe='')}&orgId=1"
