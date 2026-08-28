"""The calibration ledger: one real injected defect per gate, run through the real gate, and the
catch or the miss pushed to Grafana. A gate that has caught nothing in 7 days is ADVISORY in the
verdict; this is what gives a gate the right to block.

    python -m airlock.calibrate            # all gates
    python -m airlock.calibrate --gate claim

Defects (assets/synthetic/calibration and assets/real, built by scripts/make_synthetic_asset.sh):
  rights      the Crest excerpt: a real trademark the registry does not clear, real faces without release
  claim       the Nimbus test clip: an expert endorsement with nothing behind it (16 CFR 255.3)
  brand       the Nimbus clip with a pure red urgency banner the charter forbids
  provenance  the Nimbus clip with its manifest stripped, and a signed copy with one byte flipped
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from airlock.gates import brand, claim, provenance, rights
from airlock.gates.base import GATES, Asset, GateResult, run_gate
from airlock.telemetry import InfluxPusher, LokiPusher, line

BUCKET = os.environ.get("AIRLOCK_ASSETS_BUCKET", "airlock-agentic-cinema-assets")


@dataclass(frozen=True)
class Defect:
    gate: str
    name: str
    local_path: str
    gcs_uri: str
    expected_status: str
    expected_rule_substring: str  # the catch must name the right rule, not just say BLOCK


DEFECTS: list[Defect] = [
    Defect("rights", "real trademark not cleared, faces without release", "assets/real/CrestToothpa-18-48.mp4",
           f"gs://{BUCKET}/real/CrestToothpa-18-48.mp4", "BLOCK", "registry:brands:not_cleared"),
    Defect("claim", "expert endorsement with no substantiation", "assets/synthetic/nimbus-test-clip.mp4",
           f"gs://{BUCKET}/synthetic/nimbus-test-clip.mp4", "BLOCK", "16 CFR 255.3"),
    Defect("brand", "forbidden red banner and urgency copy", "assets/synthetic/calibration/nimbus-defect-brand-red.mp4",
           f"gs://{BUCKET}/calibration/nimbus-defect-brand-red.mp4", "BLOCK", "charter:"),
    Defect("provenance", "manifest stripped", "assets/synthetic/calibration/nimbus-defect-provenance-stripped.mp4",
           f"gs://{BUCKET}/calibration/nimbus-defect-provenance-stripped.mp4", "BLOCK", "manifest-required"),
    Defect("provenance", "signed copy with one byte flipped", "assets/synthetic/calibration/nimbus-defect-provenance-broken.mp4",
           f"gs://{BUCKET}/calibration/nimbus-defect-provenance-broken.mp4", "BLOCK", "signature-valid"),
]

CHECKS: dict[str, tuple[Callable[[Asset], GateResult], str]] = {
    "rights": (rights.check, rights.SOURCE_OF_TRUTH),
    "claim": (claim.check, claim.SOURCE_OF_TRUTH),
    "brand": (brand.check, brand.SOURCE_OF_TRUTH),
    "provenance": (provenance.check, provenance.SOURCE_OF_TRUTH),
}


def run_defect(defect: Defect) -> dict[str, Any]:
    path = defect.local_path if os.path.exists(defect.local_path) else ""
    asset = Asset(asset_id=f"calibration-{defect.gate}-{defect.name.split(',')[0].replace(' ', '-')}", path=path, gcs_uri=defect.gcs_uri)
    fn, source = CHECKS[defect.gate]
    result = run_gate(defect.gate, fn, asset, source)
    caught = result.status == defect.expected_status and any(defect.expected_rule_substring in r for r in result.rule_ids)
    return {"gate": defect.gate, "defect": defect.name, "expected": defect.expected_status, "got": result.status,
            "rule_ids": result.rule_ids, "caught": caught, "elapsed_ms": result.elapsed_ms, "reason": (result.reasons or [""])[0][:200]}


def push_ledger(rows: list[dict[str, Any]]) -> None:
    influx = InfluxPusher.from_env() if os.environ.get("GRAFANA_INFLUX_URL") else None
    loki = LokiPusher.from_env() if os.environ.get("GRAFANA_LOKI_URL") else None
    lines = []
    for r in rows:
        lines.append(line("airlock_calibration", {"gate": r["gate"]}, {"catches_total": 1 if r["caught"] else 0, "misses_total": 0 if r["caught"] else 1, "runs_total": 1}))
        if loki is not None:
            loki.push_event({"gate": r["gate"], "stage": "calibration", "runtime": os.environ.get("AIRLOCK_RUNTIME", "local")}, r)
    if influx is not None:
        influx.push_lines(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gate", choices=GATES, default=None)
    ap.add_argument("--no-push", action="store_true", help="run the defects, push nothing")
    args = ap.parse_args()
    defects = [d for d in DEFECTS if not args.gate or d.gate == args.gate]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=len(defects)) as pool:
        rows = list(pool.map(run_defect, defects))
    if not args.no_push:
        push_ledger(rows)
    for r in rows:
        print(f"{r['gate']:<11} {'CAUGHT' if r['caught'] else 'MISSED':<7} {r['elapsed_ms']:>6} ms  {r['defect']}  ->  {r['got']} {r['rule_ids'][:2]}")
    caught = sum(1 for r in rows if r["caught"])
    print(json.dumps({"defects": len(rows), "caught": caught, "missed": len(rows) - caught, "elapsed_s": round(time.time() - t0, 1), "pushed": not args.no_push}))


if __name__ == "__main__":
    main()
