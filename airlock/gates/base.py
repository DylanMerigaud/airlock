"""What every gate returns, and the envelope that times it and reports it to Grafana.

A gate never returns silently: an exception becomes status ERROR with the exception text as the
reason, the errors counter goes up, and the Loki event carries the traceback head. The verdict
agent (M3) treats ERROR like a degraded control: it cannot contribute to a PASS.
"""

from __future__ import annotations

import logging
import os
import time
import traceback
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Literal

from airlock.telemetry import MEASUREMENT, InfluxPusher, LokiPusher, line

log = logging.getLogger("airlock.gates")

Status = Literal["PASS", "BLOCK", "ERROR"]
GATES = ("rights", "claim", "brand", "provenance")


@dataclass
class Asset:
    """One asset under review: a local path and, when uploaded, its GCS URI."""

    asset_id: str
    path: str
    gcs_uri: str | None = None
    mime_type: str = "video/mp4"


@dataclass
class GateResult:
    gate: str
    status: Status
    reasons: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    source_of_truth: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


GateFn = Callable[[Asset], GateResult]


def _pushers() -> tuple[InfluxPusher | None, LokiPusher | None]:
    """Telemetry is on when the env is there; a missing env is reported once, not swallowed."""
    influx = loki = None
    if os.environ.get("GRAFANA_INFLUX_URL"):
        influx = InfluxPusher.from_env()
    else:
        log.warning("GRAFANA_INFLUX_URL not set: gate counters are not pushed")
    if os.environ.get("GRAFANA_LOKI_URL"):
        loki = LokiPusher.from_env()
    else:
        log.warning("GRAFANA_LOKI_URL not set: gate events are not pushed")
    return influx, loki


def run_gate(gate: str, fn: GateFn, asset: Asset, source_of_truth: str) -> GateResult:
    """Run one gate with timing, counters and an event, turning any exception into ERROR."""
    influx, loki = _pushers()
    t0 = time.time()
    try:
        result = fn(asset)
        result.gate = gate
        result.source_of_truth = result.source_of_truth or source_of_truth
    except Exception as exc:  # the whole point: an instrument that fails says so
        result = GateResult(
            gate=gate,
            status="ERROR",
            reasons=[f"{type(exc).__name__}: {exc}"],
            evidence=[{"traceback": traceback.format_exc()[-1500:]}],
            source_of_truth=source_of_truth,
        )
    result.elapsed_ms = int((time.time() - t0) * 1000)
    ok = result.status != "ERROR"
    if influx is not None:
        fields: dict[str, int | float] = {"runs_total": 1, "errors_total": 0 if ok else 1, "elapsed_ms": result.elapsed_ms,
                                          "blocks_total": 1 if result.status == "BLOCK" else 0}
        if ok:
            fields["last_success_ts"] = int(time.time())
        influx.push_lines([line(MEASUREMENT, {"gate": gate}, fields)])
    if loki is not None:
        loki.push_event({"gate": gate, "status": result.status, "runtime": os.environ.get("AIRLOCK_RUNTIME", "local")},
                        {"asset_id": asset.asset_id, **result.to_dict()})
    return result
