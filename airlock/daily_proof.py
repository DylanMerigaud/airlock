"""The daily proof: the control proves itself on a schedule.

The verdict trusts a gate only if Grafana has seen it catch an injected defect in the last 7 days
(rule R2, airlock/verdict.py). A calibration nobody runs expires: every gate turns "uncalibrated",
every run ends in BLOCK, the 7-day stats read zero. So a Cloud Run job (infra/gcp/daily_proof.sh)
runs this module every 12 hours; it is also what scripts/demo_prep.sh runs with --proof.

    python -m airlock.daily_proof              # calibrate every gate, run the clean clip, print one JSON line
    python -m airlock.daily_proof --no-push    # the same, nothing pushed to Grafana

In order:
  1. the calibration inputs are downloaded from GCS into the paths airlock.calibrate expects, when missing
  2. the full calibration runs (one real injected defect per gate, the catch or the miss pushed to Grafana)
  3. the clean clip runs through the deployed Agent Engine pipeline (:streamQuery, airlock.engine_client)
  4. one JSON summary line; exit 0 only if every defect was CAUGHT and the verdict is PASS, 1 otherwise,
     and one sample airlock_daily_proof_total{outcome="pass"|"fail"} pushed so the dashboard can show it

A failed proof is a fact on the dashboard, not a retry: the gate that missed loses its right to PASS
on its own until a calibration catches again.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from airlock import calibrate
from airlock.engine_client import describe, resource_from_env, stream_query
from airlock.gates.base import GATES
from airlock.telemetry import InfluxPusher, LokiPusher, line

BUCKET = os.environ.get("AIRLOCK_ASSETS_BUCKET", "airlock-agentic-cinema-assets")
CLEAN_CLIP = f"gs://{BUCKET}/calibration/nimbus-clean-clip.mp4"
PROOF_ASSET_ID = "daily-proof-nimbus-clean-clip"
MEASUREMENT = "airlock_daily_proof"


def ensure_inputs(defects: list[calibrate.Defect] | None = None, clean_inputs: dict[str, tuple[str, str]] | None = None,
                  download: Callable[[str, str], str] | None = None) -> list[str]:
    """Download every calibration input missing from the working tree. Returns the paths fetched."""
    defects = calibrate.DEFECTS if defects is None else defects
    clean_inputs = calibrate.CLEAN_INPUTS if clean_inputs is None else clean_inputs
    if download is None:
        from airlock.assets import download as gcs_download

        download = gcs_download
    wanted: dict[str, str] = {d.local_path: d.gcs_uri for d in defects}
    wanted.update({path: uri for path, uri in clean_inputs.values()})
    fetched: list[str] = []
    for local_path, gcs_uri in sorted(wanted.items()):
        if os.path.exists(local_path):
            continue
        dest_dir = os.path.dirname(local_path) or "."
        os.makedirs(dest_dir, exist_ok=True)
        got = download(gcs_uri, dest_dir)
        if os.path.abspath(got) != os.path.abspath(local_path):  # the blob's basename is the local one today; keep the contract explicit
            os.replace(got, local_path)
        fetched.append(local_path)
    return fetched


def run_calibration() -> list[dict[str, Any]]:
    """The full ledger, the way `python -m airlock.calibrate` runs it: every defect, in parallel. Not pushed here."""
    with ThreadPoolExecutor(max_workers=len(calibrate.DEFECTS)) as pool:
        rows = list(pool.map(calibrate.run_defect, calibrate.DEFECTS))
    for r in rows:
        print(f"{r['gate']:<11} {'CAUGHT' if r['caught'] else 'MISSED':<7} {r['elapsed_ms']:>6} ms  {r['defect']}  ->  {r['got']} {r['rule_ids'][:2]}", flush=True)
    return rows


def run_clean_clip(resource: str, timeout_s: float = 900) -> dict[str, Any] | None:
    """The clean clip through the deployed pipeline; returns the verdict payload, None if none came."""
    message = json.dumps({"gcs_uri": CLEAN_CLIP, "asset_id": PROOF_ASSET_ID})
    verdict: dict[str, Any] | None = None
    for ev in stream_query(resource, message, timeout_s=timeout_s):
        if ev.error:
            print(f"[{ev.t:6.1f}s] {ev.author:<16} error: {ev.error[:300]}", flush=True)
        for payload in ev.payloads():
            print(describe(ev.author, payload, ev.t), flush=True)
            if payload.get("stage") == "verdict":
                verdict = payload
    return verdict


@dataclass
class Summary:
    """What one proof established. `outcome` is "pass" only when every defect was CAUGHT and the verdict is PASS."""

    gates: dict[str, str]  # gate -> CAUGHT or MISSED (a gate with two defects is CAUGHT only if both were)
    verdict: str | None
    motive: str | None
    annotation_id: int | None
    cost_usd: float | None  # the whole proof at list price: the calibration runs plus the clean clip run
    elapsed_s: dict[str, float]
    outcome: str
    reasons: list[str] = field(default_factory=list)
    calibration: list[dict[str, Any]] = field(default_factory=list)
    calibration_cost_usd: float | None = None
    clean_clip_cost_usd: float | None = None

    @property
    def exit_code(self) -> int:
        return 0 if self.outcome == "pass" else 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize(rows: list[dict[str, Any]], verdict: dict[str, Any] | None, elapsed_s: dict[str, float],
              failures: list[str] | None = None) -> Summary:
    """Judge the proof: every gate CAUGHT its defect(s), the pipeline said PASS on the clean clip, and
    nothing else went wrong on the way (`failures`: a ledger that could not be pushed, for one)."""
    reasons: list[str] = list(failures or [])
    gates: dict[str, str] = {}
    for gate in GATES:
        mine = [r for r in rows if r.get("gate") == gate]
        if not mine:
            gates[gate] = "MISSED"
            reasons.append(f"{gate}: no calibration row")
            continue
        missed = [r for r in mine if not r.get("caught")]
        gates[gate] = "MISSED" if missed else "CAUGHT"
        for r in missed:
            reasons.append(f"{gate}: MISSED {r.get('defect')} (got {r.get('got')} {list(r.get('rule_ids') or [])[:2]})")
    if verdict is None:
        reasons.append("no verdict event from Agent Engine")
        status = motive = annotation_id = clean_cost = None
    else:
        status = verdict.get("status")
        motive = verdict.get("motive")
        annotation_id = verdict.get("annotation_id")
        clean_cost = (verdict.get("cost") or {}).get("cost_usd")
        if status != "PASS":
            first = (verdict.get("reasons") or [""])[0]
            reasons.append(f"verdict {status} ({motive}): {first[:200]}")
    priced = [float(r["cost_usd"]) for r in rows if r.get("cost_usd") is not None]
    calibration_cost = round(sum(priced), 6) if priced else None
    cost_usd = None if calibration_cost is None and clean_cost is None else round((calibration_cost or 0.0) + (clean_cost or 0.0), 6)
    calibration = [{k: r.get(k) for k in ("gate", "defect", "caught", "got", "elapsed_ms", "cost_usd")} for r in rows]
    return Summary(gates=gates, verdict=status, motive=motive, annotation_id=annotation_id, cost_usd=cost_usd,
                   elapsed_s={k: round(v, 1) for k, v in elapsed_s.items()}, outcome="pass" if not reasons else "fail",
                   reasons=reasons, calibration=calibration, calibration_cost_usd=calibration_cost, clean_clip_cost_usd=clean_cost)


def proof_line(outcome: str, ts_ns: int | None = None, cost_usd: float | None = None) -> str:
    """airlock_daily_proof,outcome=pass total=1i,cost_usd=1.01: the series airlock_daily_proof_total{outcome="pass"}
    and airlock_daily_proof_cost_usd{outcome="pass"} in Grafana (the cost field only when the proof priced itself)."""
    fields: dict[str, int | float] = {"total": 1}
    if cost_usd is not None:
        fields["cost_usd"] = cost_usd
    return line(MEASUREMENT, {"outcome": outcome}, fields, ts_ns=ts_ns)


def push_proof(summary: Summary) -> None:
    if os.environ.get("GRAFANA_INFLUX_URL"):
        InfluxPusher.from_env().push_lines([proof_line(summary.outcome, cost_usd=summary.cost_usd)])
    if os.environ.get("GRAFANA_LOKI_URL"):
        LokiPusher.from_env().push_event({"stage": "daily_proof", "outcome": summary.outcome,
                                          "runtime": os.environ.get("AIRLOCK_RUNTIME", "local")}, summary.to_dict())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--resource", default=resource_from_env(), help="the reasoning engine (env AGENT_ENGINE_RESOURCE)")
    ap.add_argument("--no-push", action="store_true", help="push nothing to Grafana (the calibration ledger nor the proof)")
    ap.add_argument("--timeout", type=float, default=900, help="seconds to wait for the pipeline's stream")
    args = ap.parse_args(argv)
    elapsed: dict[str, float] = {}

    t0 = time.time()
    fetched = ensure_inputs()
    elapsed["inputs"] = time.time() - t0
    print(f"inputs: {len(fetched)} downloaded" + (f" ({', '.join(fetched)})" if fetched else ", all present"), flush=True)

    failures: list[str] = []
    t0 = time.time()
    rows = run_calibration()
    if not args.no_push:
        try:
            calibrate.push_ledger(rows)
        except Exception as exc:  # a ledger Grafana did not receive leaves the gates uncalibrated: the proof failed
            failures.append(f"calibration ledger not pushed: {type(exc).__name__}: {exc}")
    elapsed["calibration"] = time.time() - t0

    t0 = time.time()
    verdict: dict[str, Any] | None = None
    try:
        verdict = run_clean_clip(args.resource, timeout_s=args.timeout)
    except Exception as exc:  # the proof must end in a summary line, with the failure named
        failures.append(f"clean clip run failed: {type(exc).__name__}: {exc}")
    elapsed["clean_clip"] = time.time() - t0

    summary = summarize(rows, verdict, elapsed, failures)
    if not args.no_push:
        try:
            push_proof(summary)
        except Exception as exc:
            print(f"proof metric not pushed: {type(exc).__name__}: {exc}", flush=True)
    print(json.dumps(summary.to_dict(), default=str), flush=True)
    if summary.exit_code:
        print("daily proof FAILED: " + "; ".join(summary.reasons), flush=True)
    return summary.exit_code


if __name__ == "__main__":
    sys.exit(main())
