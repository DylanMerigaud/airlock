"""Run the four gates on one asset and print what each one found.

    python -m airlock.run assets/real/CrestToothpa.mp4
    python -m airlock.run assets/synthetic/nimbus-test-clip.mp4 --json

Telemetry goes to Grafana when the env is loaded (scripts/with_env.sh). The verdict (M3) is not
here: this is the gates alone, which is what a reviewer needs to read first.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

from airlock.gates import CHECKS, GATES
from airlock.gates.base import Asset, GateResult, run_gate


def make_asset(path: str, gcs_uri: str | None = None) -> Asset:
    p = pathlib.Path(path)
    if not p.exists():
        sys.exit(f"no such file: {path}")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    return Asset(asset_id=f"{p.stem}-{digest}", path=str(p), gcs_uri=gcs_uri)


def run_all(asset: Asset, only: list[str] | None = None) -> list[GateResult]:
    results = []
    for gate in GATES:
        if only and gate not in only:
            continue
        fn, source = CHECKS[gate]
        results.append(run_gate(gate, fn, asset, source))
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--gcs-uri", default=None, help="GCS URI of the same file, when already uploaded")
    ap.add_argument("--only", default=None, help="comma-separated subset of gates")
    ap.add_argument("--json", action="store_true", help="print the full JSON instead of the summary")
    args = ap.parse_args()
    asset = make_asset(args.path, args.gcs_uri)
    results = run_all(asset, args.only.split(",") if args.only else None)
    if args.json:
        print(json.dumps({"asset": asset.__dict__, "gates": [r.to_dict() for r in results]}, indent=1, default=str))
        return
    print(f"asset {asset.asset_id}")
    for r in results:
        print(f"  {r.gate:<11} {r.status:<6} {r.elapsed_ms:>6} ms  {r.reasons[0] if r.reasons else ''}")
        for rid in r.rule_ids[:4]:
            print(f"  {'':<11} {'':<6} {'':>6}     rule {rid}")


if __name__ == "__main__":
    main()
