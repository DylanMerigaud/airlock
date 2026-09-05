"""What every gate returns, and the envelope that times it and reports it to Grafana.

A gate never returns silently: an exception becomes status ERROR with the exception text as the
reason, the errors counter goes up, and the Loki event carries the traceback head. The verdict
agent (M3) treats ERROR like a degraded control: it cannot contribute to a PASS.

Every Loki event carries the asset id and the run id (the ADK invocation id), so the verdict can
ask Grafana for THIS run's event of each gate, not for some run's. The run id is a body field, not
a label: one label value per run would be one Loki stream per run.
"""

from __future__ import annotations

import logging
import os
import time
import traceback
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Literal

from airlock.cost import estimate
from airlock.telemetry import MEASUREMENT, InfluxPusher, LokiPusher, line

log = logging.getLogger("airlock.gates")

Status = Literal["PASS", "BLOCK", "ERROR"]
GATES = ("rights", "claim", "brand", "provenance")


@dataclass
class Asset:
    """One asset under review: a local path and, when uploaded, its GCS URI.

    run_id names the run that reads it (the pipeline sets the ADK invocation id); it travels in
    every Loki event so the verdict can find this run's events and no other's."""

    asset_id: str
    path: str
    gcs_uri: str | None = None
    mime_type: str = "video/mp4"
    run_id: str | None = None


@dataclass
class GateResult:
    gate: str
    status: Status
    reasons: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    source_of_truth: str = ""
    usage: dict[str, Any] = field(default_factory=dict)

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


def muted(gate: str) -> bool:
    """AIRLOCK_MUTE_GATE_TELEMETRY=rights,claim silences a gate's pushes: the M3 test of the rule
    "control unavailable" (Grafana stops seeing the gate succeed, the verdict must refuse to PASS)."""
    return gate in {x.strip() for x in os.environ.get("AIRLOCK_MUTE_GATE_TELEMETRY", "").split(",") if x.strip()}


FAULT_TIMEOUT = "timeout"


def inject_fault(fault: str, gate: str, run_id: str | None) -> None:
    """Raise the injected fault before the gate spends anything. The judge's second action: the input
    carries {"fault": {"rights": "timeout"}}, the gate fails the way a real timeout would (ERROR in
    Loki and in the errors counter, with the run id), and the verdict has to notice through Grafana."""
    if fault == FAULT_TIMEOUT:
        raise TimeoutError(f"Video Intelligence operation timed out after 1 s (fault injected for run {run_id})")
    raise ValueError(f"unknown fault {fault!r} injected for gate {gate} on run {run_id}")


def run_gate(gate: str, fn: GateFn, asset: Asset, source_of_truth: str, mute: bool | None = None, fault: str | None = None) -> GateResult:
    """Run one gate with timing, counters and an event, turning any exception into ERROR.

    mute=True silences the pushes (the judge's "disable a gate" action); None falls back to the env.
    fault names an injected failure (FAULT_TIMEOUT) raised before the gate function runs.
    """
    is_muted = muted(gate) if mute is None else mute
    influx, loki = (None, None) if is_muted else _pushers()
    if is_muted:
        log.warning("gate %s telemetry is MUTED", gate)
    t0 = time.time()
    try:
        if fault:
            inject_fault(fault, gate, asset.run_id)
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
    try:
        result.usage = estimate(gate, result.evidence).to_dict()
    except Exception as exc:  # a cost that cannot be computed is said, never guessed
        result.usage = {"cost_usd": None, "error": f"{type(exc).__name__}: {exc}"}
    if influx is not None:
        fields: dict[str, int | float] = {"runs_total": 1, "errors_total": 0 if ok else 1, "elapsed_ms": result.elapsed_ms,
                                          "blocks_total": 1 if result.status == "BLOCK" else 0}
        if result.usage.get("cost_usd") is not None:
            fields["cost_usd"] = float(result.usage["cost_usd"])
            fields["tokens_in"] = int(result.usage.get("tokens_in") or 0)
            fields["tokens_out"] = int(result.usage.get("tokens_out") or 0)
            fields["video_minutes"] = float(result.usage.get("video_minutes") or 0)
        if ok:
            fields["last_success_ts"] = int(time.time())
        influx.push_lines([line(MEASUREMENT, {"gate": gate}, fields)])
    if loki is not None:
        loki.push_event({"gate": gate, "status": result.status, "runtime": os.environ.get("AIRLOCK_RUNTIME", "local")},
                        loki_event(asset, result, fault))
    return result


def loki_event(asset: Asset, result: GateResult, fault: str | None = None) -> dict[str, Any]:
    """The body of a gate's Loki event: the result, the asset id, the run id, and the injected fault when there was one."""
    body: dict[str, Any] = {"asset_id": asset.asset_id, "run_id": asset.run_id, **result.to_dict()}
    if fault:
        body["fault"] = fault
    return body
