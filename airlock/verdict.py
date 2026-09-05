"""The verdict: deterministic rules over the gate results and over what Grafana says about each gate.

The rules, in plain Python and unit-tested; the ADK agent (agents/pipeline) is the envelope that
asks Grafana the five questions per gate through mcp-grafana and writes the annotation.

Five questions per gate, the first to Loki (LogQL), the other four to Prometheus (PromQL over the
counters the gates push; the second in two parts):
  1. seen this run: does Loki hold THIS run's event of this gate ({app="airlock", gate=...} |= run_id)
  2. error ratio over 15 min           errors / runs, and the number of runs it rests on
  3. seconds since the last success    time() - last_success_ts (informational: it feeds the health
                                       line and the console, never the rule; the run itself is the freshness proof)
  4. calibration catches over 7 days
  5. whether the LAST calibration run caught its defect

Two rules:
  R1 "control unavailable": a gate whose event for this run Grafana cannot see, or whose own
     result is ERROR, or whose recent runs are mostly errors (ratio at least ERROR_RATIO_BLOCK over
     at least ERROR_RUNS_MIN runs), forces BLOCK. The gate's own self-report does not count;
     Grafana's view of it does. A muted gate pushes nothing to Loki, so its run event is not
     seen, so R1 fires by construction, whatever the gate said. A single transient error no longer
     freezes every asset for 15 minutes: one error in two runs is a majority, one in three is not.
  R2 "uncalibrated": a gate with zero calibration catches in the window, or whose last calibration
     run missed its defect, is ADVISORY; its PASS cannot contribute to a PASS verdict. Its BLOCK still
     blocks (a doubtful instrument that says no is still no).
A PASS needs all four gates PASS, seen, healthy and calibrated. A BLOCK needs a human when it comes
from the state of a control (R1, R2) or from missing paperwork a person can supply (a substantiation,
a licence, a release, a signer to trust); a BLOCK on a defect of the asset itself (no manifest,
broken signature, off-charter, explicit content) needs no arbitration. When the verdict agent itself
cannot complete (Grafana unreachable beyond the wake budget), the verdict is ERROR "instrument error",
also a human's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from airlock.gates.base import GATES

STALE_AFTER_S = 15 * 60  # the console's "idle" threshold on seconds since success; not a rule input since 2026-09-05
ERROR_WINDOW = "15m"
ERROR_RATIO_BLOCK = 0.5
ERROR_RUNS_MIN = 2
CALIBRATION_WINDOW = "7d"
RUN_EVENT_WINDOW_MIN = 30
PAPERWORK_RULE_PREFIXES = ("16 CFR", "ASA ", "registry:brands:not_cleared", "registry:brands:unknown", "registry:faces:no_release", "airlock:provenance:signer-trusted")


def needs_paperwork(rule_ids: list[str]) -> bool:
    return any(r.startswith(p) for r in rule_ids for p in PAPERWORK_RULE_PREFIXES)


VerdictStatus = Literal["PASS", "BLOCK"]
Motive = Literal["content", "control unavailable", "uncalibrated control", "instrument error"]


def promql_questions(gate: str) -> dict[str, str]:
    """The PromQL questions asked about one gate, keyed by the name the health line uses."""
    return {
        "error_rate_15m": f'sum(sum_over_time(airlock_gate_errors_total{{gate="{gate}"}}[{ERROR_WINDOW}])) / clamp_min(sum(sum_over_time(airlock_gate_runs_total{{gate="{gate}"}}[{ERROR_WINDOW}])), 1)',
        "runs_15m": f'sum(sum_over_time(airlock_gate_runs_total{{gate="{gate}"}}[{ERROR_WINDOW}]))',
        "seconds_since_success": f'time() - max(max_over_time(airlock_gate_last_success_ts{{gate="{gate}"}}[{CALIBRATION_WINDOW}]))',
        "calibration_catches_7d": f'sum(sum_over_time(airlock_calibration_catches_total{{gate="{gate}"}}[{CALIBRATION_WINDOW}]))',
        # min over the series so that, once the ledger carries one series per defect, a gate with two
        # defects reads as caught only when its LAST sample of every defect is a catch
        "last_calibration_caught": f'min by () (last_over_time(airlock_calibration_catches_total{{gate="{gate}"}}[{CALIBRATION_WINDOW}]))',
    }


def logql_question(gate: str, run_id: str) -> str:
    """The Loki question: this run's event of this gate. The run id is a body field, so a line filter finds it."""
    return f'{{app="airlock", gate="{gate}"}} |= "{run_id}"'


@dataclass
class GateHealth:
    """What Grafana answered for one gate. None means the query returned no sample (or was not asked)."""

    gate: str
    error_rate_15m: float | None
    seconds_since_success: float | None
    calibration_catches_7d: float | None
    last_calibration_caught: float | None = None  # 1 caught, 0 missed, None never calibrated
    seen_this_run: bool | None = None  # True: Loki holds this run's event of the gate; False: no event; None: Loki could not be read
    runs_15m: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def errors_are_majority(self) -> bool:
        return (self.error_rate_15m is not None and self.error_rate_15m >= ERROR_RATIO_BLOCK
                and (self.runs_15m or 0) >= ERROR_RUNS_MIN)

    @property
    def unavailable(self) -> bool:
        """R1 from Grafana's side: this run's event is not seen (None counts as not seen: fail closed),
        or the recent runs are mostly errors."""
        if not self.seen_this_run:
            return True
        return self.errors_are_majority

    @property
    def calibrated(self) -> bool:
        if (self.calibration_catches_7d or 0) <= 0:
            return False
        return self.last_calibration_caught is None or self.last_calibration_caught > 0

    def calibration_note(self) -> str:
        if (self.calibration_catches_7d or 0) <= 0:
            return f"no injected defect caught in {CALIBRATION_WINDOW}"
        if self.last_calibration_caught is not None and self.last_calibration_caught <= 0:
            return f"last calibration run MISSED its defect ({int(self.calibration_catches_7d)} caught earlier in {CALIBRATION_WINDOW})"
        return f"caught {int(self.calibration_catches_7d)} injected defect(s) in {CALIBRATION_WINDOW}"

    def describe(self) -> str:
        if self.seen_this_run is None:
            return "this run's event could not be read from Grafana"
        if not self.seen_this_run:
            return "NOT seen by Grafana for this run"
        parts = ["seen by Grafana for this run"]
        if self.errors_are_majority:
            parts.append(f"error rate {self.error_rate_15m:.0%} over {ERROR_WINDOW} ({int(self.runs_15m or 0)} runs)")
        elif self.error_rate_15m:
            parts.append(f"error rate {self.error_rate_15m:.0%} over {ERROR_WINDOW}, under the {ERROR_RATIO_BLOCK:.0%} block line")
        if self.seconds_since_success is None:
            parts.append("no success sample in Grafana")
        else:
            parts.append(f"last success {int(self.seconds_since_success)} s ago")
        return ", ".join(parts)


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
    paperwork_block = False
    control_block = False
    advisory_pass = False
    for gate in GATES:
        r = gate_results.get(gate) or {}
        h = health.get(gate)
        status = r.get("status", "ERROR")
        line = {"gate": gate, "status": status, "reason": (r.get("reasons") or [""])[0],
                "health": h.describe() if h else "no health data", "calibrated": bool(h and h.calibrated),
                "calibration": h.calibration_note() if h else "no calibration data",
                "calibration_catches_7d": h.calibration_catches_7d if h else None,
                "seen_this_run": h.seen_this_run if h else None,
                "rule_ids": r.get("rule_ids", [])}
        lines.append(line)
        if status == "ERROR":
            control_block = True
            reasons.append(f"{gate}: control unavailable (instrument error: {line['reason']}; {line['health']})")
            rule_ids.append("airlock:verdict:R1-control-unavailable")
            rule_ids.append("airlock:verdict:instrument-error")
            continue
        if h is None or h.unavailable:
            control_block = True
            reasons.append(f"{gate}: control unavailable ({line['health']})")
            rule_ids.append("airlock:verdict:R1-control-unavailable")
        if status == "BLOCK":
            content_block = True
            paperwork_block = paperwork_block or needs_paperwork(r.get("rule_ids", []))
            reasons.append(f"{gate}: BLOCK, {line['reason']}")
            for rid in r.get("rule_ids", [])[:3]:
                if rid not in rule_ids:
                    rule_ids.append(rid)
        elif h is not None and not h.calibrated:
            advisory_pass = True
            reasons.append(f"{gate}: PASS is advisory only, {h.calibration_note()}")
            rule_ids.append("airlock:verdict:R2-uncalibrated")
    if content_block:
        if paperwork_block:
            reasons.append("a human can lift this BLOCK by supplying the missing substantiation, licence or release")
        return Verdict("BLOCK", "content", paperwork_block or control_block, reasons, lines, sorted(set(rule_ids)))
    if control_block:
        return Verdict("BLOCK", "control unavailable", True, reasons, lines, sorted(set(rule_ids)))
    if advisory_pass:
        return Verdict("BLOCK", "uncalibrated control", True, reasons, lines, sorted(set(rule_ids)))
    return Verdict("PASS", "content", False, [f"all {len(GATES)} gates PASS, seen by Grafana, healthy and calibrated"], lines, ["airlock:verdict:all-gates-pass"])
