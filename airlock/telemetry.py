"""Push gate metrics to Grafana Cloud through the InfluxDB line-protocol endpoint, and events
through the Loki push API.

Each field of a measurement becomes one Prometheus series named
``<measurement>_<field>`` with the line's tags as labels. The push is a plain
HTTP POST; no Prometheus client, no remote write, no protobuf.

Environment (airlock.settings names them; none has a default, unset means "not configured"):
  GRAFANA_INFLUX_URL    e.g. https://influx-prod-XX-prod-us-east-0.grafana.net/api/v1/push/influx/write
  GRAFANA_INFLUX_USER   the metrics instance id of the stack
  GRAFANA_INFLUX_TOKEN  a Cloud Access Policy token with the metrics:write scope
  GRAFANA_LOKI_URL, GRAFANA_LOKI_USER, GRAFANA_LOKI_TOKEN   the same for the logs instance

One process holds one pusher of each kind: shared_pushers() builds them from the environment on
first use (an httpx.Client each, thread-safe, reused by every gate run, every calibration row and
every proof) and close_shared_pushers() closes them at exit. Before 2026-09-05 every gate run built
two clients and closed neither.
"""

from __future__ import annotations

import atexit
import json
import logging
import threading
import time
from dataclasses import dataclass, field

import httpx

from airlock import settings

log = logging.getLogger("airlock.telemetry")

MEASUREMENT = "airlock_gate"


def _escape_tag(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(" ", "\\ ").replace("=", "\\=")


def line(measurement: str, tags: dict[str, str], fields: dict[str, int | float], ts_ns: int | None = None) -> str:
    """Format one InfluxDB line-protocol line. Integers get the ``i`` suffix."""
    if not fields:
        raise ValueError("a line needs at least one field")
    tag_part = "".join(f",{_escape_tag(k)}={_escape_tag(str(v))}" for k, v in sorted(tags.items()))
    field_parts = []
    for k, v in sorted(fields.items()):
        if isinstance(v, bool):
            raise TypeError("bool fields are ambiguous, push 0 or 1")
        field_parts.append(f"{k}={v}i" if isinstance(v, int) else f"{k}={v}")
    stamp = ts_ns if ts_ns is not None else time.time_ns()
    return f"{measurement}{tag_part} {','.join(field_parts)} {stamp}"


@dataclass
class InfluxPusher:
    url: str
    user: str
    token: str
    timeout_s: float = 10.0
    client: httpx.Client = field(default_factory=httpx.Client, repr=False)

    @classmethod
    def from_env(cls) -> InfluxPusher:
        ep = settings.influx()
        if ep.missing():
            raise RuntimeError(f"missing env: {', '.join(ep.missing())}")
        return cls(url=ep.url, user=ep.user, token=ep.token)

    def close(self) -> None:
        self.client.close()

    def push_lines(self, lines: list[str]) -> int:
        """POST the lines. Returns the HTTP status; raises on a non-2xx answer."""
        body = "\n".join(lines) + "\n"
        resp = self.client.post(
            self.url,
            content=body.encode(),
            headers={"Authorization": f"Bearer {self.user}:{self.token}", "Content-Type": "text/plain; charset=utf-8"},
            timeout=self.timeout_s,
        )
        if resp.status_code >= 300:
            raise RuntimeError(f"influx push failed: HTTP {resp.status_code} {resp.text[:300]}")
        return resp.status_code


LOKI_PATH = "/loki/api/v1/push"
# The stack's Loki datasource is provisioned read-only by Grafana Cloud (PUT answers 403 "Cannot update read-only
# data source", measured 2026-09-05) and ships one derived field, traceID, whose regex
# [tT]race_?[iI][dD]"?[:=]"?(\w+) links a line to Tempo. It matches "trace_id":"<id>" and not "trace_id": "<id>":
# the lines are written without the space so the stack's own link works on them, no datasource edit needed.
LOKI_SEPARATORS = (",", ":")


def loki_line(event: dict) -> str:
    """One Loki line: the event as compact JSON (the derived field regex above needs no space after the colon)."""
    return json.dumps(event, default=str, separators=LOKI_SEPARATORS)


@dataclass
class LokiPusher:
    """Push one JSON event per agent step to Grafana Cloud Logs (Loki push API)."""

    url: str
    user: str
    token: str
    timeout_s: float = 10.0
    client: httpx.Client = field(default_factory=httpx.Client, repr=False)

    @classmethod
    def from_env(cls) -> LokiPusher:
        ep = settings.loki()
        if ep.missing():
            raise RuntimeError(f"missing env: {', '.join(ep.missing())}")
        return cls(url=ep.url.rstrip("/") + LOKI_PATH, user=ep.user, token=ep.token)

    def close(self) -> None:
        self.client.close()

    def push_event(self, labels: dict[str, str], event: dict) -> int:
        body = {"streams": [{"stream": {"app": "airlock", **labels}, "values": [[str(time.time_ns()), loki_line(event)]]}]}
        resp = self.client.post(self.url, json=body, auth=(self.user, self.token), timeout=self.timeout_s)
        if resp.status_code >= 300:
            raise RuntimeError(f"loki push failed: HTTP {resp.status_code} {resp.text[:300]}")
        return resp.status_code


_shared_lock = threading.Lock()
_shared: tuple[InfluxPusher | None, LokiPusher | None] | None = None
_shared_closer_registered = False


def shared_pushers() -> tuple[InfluxPusher | None, LokiPusher | None]:
    """The process's one Influx pusher and one Loki pusher, built from the environment on first call.

    Either is None when its endpoint is not configured (GRAFANA_INFLUX_URL or GRAFANA_LOKI_URL unset),
    and that is said once in the log, not swallowed. A URL set with its user or token missing raises:
    half a configuration is an error, not silence.
    """
    global _shared, _shared_closer_registered
    with _shared_lock:
        if _shared is None:
            influx = loki = None
            if settings.influx().configured:
                influx = InfluxPusher.from_env()
            else:
                log.warning("GRAFANA_INFLUX_URL not set: gate counters are not pushed")
            if settings.loki().configured:
                loki = LokiPusher.from_env()
            else:
                log.warning("GRAFANA_LOKI_URL not set: gate events are not pushed")
            _shared = (influx, loki)
            if not _shared_closer_registered:
                atexit.register(close_shared_pushers)
                _shared_closer_registered = True
        return _shared


def close_shared_pushers() -> None:
    """Close the shared clients and forget them; the next shared_pushers() call rebuilds from the environment."""
    global _shared
    with _shared_lock:
        if _shared is None:
            return
        for pusher in _shared:
            if pusher is not None:
                pusher.close()
        _shared = None
