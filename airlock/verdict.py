"""The verdict: deterministic rules over the gate results and over what Grafana says about each gate.

The rules, in plain Python and unit-tested; the ADK agent (agents/airlock) is the envelope that
asks Grafana the three questions per gate through mcp-grafana and writes the annotation.

Three questions per gate (PromQL over the counters the gates push):
  1. error rate over 15 min          errors / runs
  2. seconds since the last success   time() - last_success_ts
  3. calibration catches over 7 days  injected defects the gate actually caught

Two rules:
  R1 "control unavailable": a gate with errors in the window, or whose last success Grafana cannot
     see within STALE_AFTER_S, forces BLOCK. The gate's own self-report does not count; Grafana's
     view of it does.
  R2 "uncalibrated": a gate with zero calibration catches is ADVISORY; its PASS cannot contribute
     to a PASS verdict. Its BLOCK still blocks (a doubtful instrument that says no is still no).
A PASS needs all four gates PASS, healthy and calibrated. A BLOCK caused by the state of a control
(R1 or R2) rather than by the content needs a human, and the escalation opens an incident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from airlock.gates.base import GATES

STALE_AFTER_S = 15 * 60
ERROR_WINDOW = "15m"
CALIBRATION_WINDOW = "7d"

VerdictStatus = Literal["PASS", "BLOCK"]
Motive = Literal["content", "control unavailable", "uncalibrated control", "instrument error"]


def promql_questions(gate: str) -> dict[str, str]:
    return {
        "error_rate_15m": f'sum(sum_over_time(airlock_gate_errors_total{{gate="{gate}"}}[{ERROR_WINDOW}])) / clamp_min(sum(sum_over_time(airlock_gate_runs_total{{gate="{gate}"}}[{ERROR_WINDOW}])), 1)',
        "seconds_since_success": f'time() - max(max_over_time(airlock_gate_last_success_ts{{gate="{gate}"}}[{CALIBRATION_WINDOW}]))',
        "calibration_catches_7d": f'sum(sum_over_time(airlock_calibration_catches_total{{gate="{gate}"}}[{CALIBRATION_WINDOW}]))',
    }


@dataclass
class GateHealth:
    """What Grafana answered for one gate. None means the query returned no sample."""

    gate: str
    error_rate_15m: float | None
    seconds_since_success: float | None
    calibration_catches_7d: float | None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def unavailable(self) -> bool:
        if self.error_rate_15m is not None and self.error_rate_15m > 0:
            return True
        return self.seconds_since_success is None or self.seconds_since_success > STALE_AFTER_S

    @property
    def calibrated(self) -> bool:
        return (self.calibration_catches_7d or 0) > 0

    def describe(self) -> str:
        if self.error_rate_15m is not None and self.error_rate_15m > 0:
            return f"error rate {self.error_rate_15m:.0%} over {ERROR_WINDOW}"
        if self.seconds_since_success is None:
            return "no success sample visible in Grafana"
        if self.seconds_since_success > STALE_AFTER_S:
            return f"last success {int(self.seconds_since_success)} s ago, older than {STALE_AFTER_S} s"
        return f"healthy, last success {int(self.seconds_since_success)} s ago"


@dataclass
class Verdict:
    status: VerdictStatus
    motive: Motive
    needs_human: bool
    reasons: list[str]
    gate_lines: list[dict[str, Any]]
    rule_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "motive": self.motive, "needs_human": self.needs_human, "reasons": self.reasons,
                "gates": self.gate_lines, "rule_ids": self.rule_ids}


def decide(gate_results: dict[str, dict[str, Any]], health: dict[str, GateHealth]) -> Verdict:
    """gate_results: gate -> GateResult.to_dict(); health: gate -> GateHealth. Both keyed by gate name."""
    reasons: list[str] = []
    rule_ids: list[str] = []
    lines: list[dict[str, Any]] = []
    content_block = False
    control_block = False
    instrument_error = False
    advisory_pass = False
    for gate in GATES:
        r = gate_results.get(gate) or {}
        h = health.get(gate)
        status = r.get("status", "ERROR")
        line = {"gate": gate, "status": status, "reason": (r.get("reasons") or [""])[0],
                "health": h.describe() if h else "no health data", "calibrated": bool(h and h.calibrated),
                "calibration_catches_7d": h.calibration_catches_7d if h else None,
                "rule_ids": r.get("rule_ids", [])}
        lines.append(line)
        if status == "ERROR":
            instrument_error = True
            reasons.append(f"{gate}: instrument error, {line['reason']}")
            rule_ids.append("airlock:verdict:instrument-error")
            continue
        if h is None or h.unavailable:
            control_block = True
            reasons.append(f"{gate}: control unavailable ({line['health']})")
            rule_ids.append("airlock:verdict:R1-control-unavailable")
        if status == "BLOCK":
            content_block = True
            reasons.append(f"{gate}: BLOCK, {line['reason']}")
            for rid in r.get("rule_ids", [])[:3]:
                if rid not in rule_ids:
                    rule_ids.append(rid)
        elif h is not None and not h.calibrated:
            advisory_pass = True
            reasons.append(f"{gate}: PASS is advisory only, the gate has caught no injected defect in {CALIBRATION_WINDOW}")
            rule_ids.append("airlock:verdict:R2-uncalibrated")
    if instrument_error:
        return Verdict("BLOCK", "instrument error", True, reasons, lines, sorted(set(rule_ids)))
    if content_block:
        return Verdict("BLOCK", "content", False, reasons, lines, sorted(set(rule_ids)))
    if control_block:
        return Verdict("BLOCK", "control unavailable", True, reasons, lines, sorted(set(rule_ids)))
    if advisory_pass:
        return Verdict("BLOCK", "uncalibrated control", True, reasons, lines, sorted(set(rule_ids)))
    return Verdict("PASS", "content", False, [f"all {len(GATES)} gates PASS, healthy and calibrated"], lines, ["airlock:verdict:all-gates-pass"])
