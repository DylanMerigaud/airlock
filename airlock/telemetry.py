"""Push gate metrics to Grafana Cloud through the InfluxDB line-protocol endpoint.

Each field of a measurement becomes one Prometheus series named
``<measurement>_<field>`` with the line's tags as labels. The push is a plain
HTTP POST; no Prometheus client, no remote write, no protobuf.

Environment:
  GRAFANA_INFLUX_URL    e.g. https://influx-prod-XX-prod-us-east-0.grafana.net/api/v1/push/influx/write
  GRAFANA_INFLUX_USER   the metrics instance id of the stack
  GRAFANA_INFLUX_TOKEN  a Cloud Access Policy token with the metrics:write scope
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import httpx

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
    def from_env(cls) -> "InfluxPusher":
        missing = [k for k in ("GRAFANA_INFLUX_URL", "GRAFANA_INFLUX_USER", "GRAFANA_INFLUX_TOKEN") if not os.environ.get(k)]
        if missing:
            raise RuntimeError(f"missing env: {', '.join(missing)}")
        return cls(url=os.environ["GRAFANA_INFLUX_URL"], user=os.environ["GRAFANA_INFLUX_USER"], token=os.environ["GRAFANA_INFLUX_TOKEN"])

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

    def push_gate_run(self, gate: str, ok: bool, elapsed_ms: int) -> int:
        """One run of a gate: runs_total, errors_total, last_success_ts and elapsed_ms as fields."""
        now_s = int(time.time())
        fields: dict[str, int | float] = {"runs_total": 1, "errors_total": 0 if ok else 1, "elapsed_ms": elapsed_ms}
        if ok:
            fields["last_success_ts"] = now_s
        return self.push_lines([line(MEASUREMENT, {"gate": gate}, fields)])


LOKI_PATH = "/loki/api/v1/push"


@dataclass
class LokiPusher:
    """Push one JSON event per agent step to Grafana Cloud Logs (Loki push API)."""

    url: str
    user: str
    token: str
    timeout_s: float = 10.0
    client: httpx.Client = field(default_factory=httpx.Client, repr=False)

    @classmethod
    def from_env(cls) -> "LokiPusher":
        missing = [k for k in ("GRAFANA_LOKI_URL", "GRAFANA_LOKI_USER", "GRAFANA_LOKI_TOKEN") if not os.environ.get(k)]
        if missing:
            raise RuntimeError(f"missing env: {', '.join(missing)}")
        return cls(url=os.environ["GRAFANA_LOKI_URL"].rstrip("/") + LOKI_PATH, user=os.environ["GRAFANA_LOKI_USER"], token=os.environ["GRAFANA_LOKI_TOKEN"])

    def push_event(self, labels: dict[str, str], event: dict) -> int:
        import json

        body = {"streams": [{"stream": {"app": "airlock", **labels}, "values": [[str(time.time_ns()), json.dumps(event, default=str)]]}]}
        resp = self.client.post(self.url, json=body, auth=(self.user, self.token), timeout=self.timeout_s)
        if resp.status_code >= 300:
            raise RuntimeError(f"loki push failed: HTTP {resp.status_code} {resp.text[:300]}")
        return resp.status_code
