"""Run the four gates on the eval set: 10 real Prelinger excerpts plus 6 synthetic assets, one
asset at a time, so Video Intelligence never has two jobs running together (a second agent is
recording the demo video against the live console and shares the same project's quota).

    AIRLOCK_RUNTIME=eval scripts/with_env.sh uv run python scripts/eval_gates.py
    scripts/with_env.sh uv run python scripts/eval_gates.py --only nimbus-test-clip,veo-raw
    scripts/with_env.sh uv run python scripts/eval_gates.py --list

Takes about 2 minutes per asset (rights alone is 30 to 120 s on Video Intelligence); run the full
set in the background with the log under eval/logs/:

    scripts/with_env.sh uv run python scripts/eval_gates.py > eval/logs/run-<timestamp>.log 2>&1 &

Writes eval/results.json (every GateResult, per asset per gate: status, elapsed_ms, first reason,
rule_ids) and eval/EVAL.md (the table, precision and recall where a ground truth exists, latency).
AIRLOCK_RUNTIME=eval is set here, in-process, so the telemetry Grafana sees is labelled and does not
read as a normal console or calibration run.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

os.environ["AIRLOCK_RUNTIME"] = "eval"

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from airlock.gates.base import GATES, Asset, GateResult  # noqa: E402
from airlock.run import run_all  # noqa: E402

BUCKET = os.environ.get("AIRLOCK_ASSETS_BUCKET", "airlock-agentic-cinema-assets")
EVAL_DIR = ROOT / "eval"
RESULTS_PATH = EVAL_DIR / "results.json"
EVAL_MD_PATH = EVAL_DIR / "EVAL.md"


@dataclass(frozen=True)
class AssetSpec:
    asset_id: str
    kind: str  # "real" or "synthetic"
    local: str  # path relative to ROOT
    gcs_uri: str | None
    brand: str | None = None  # expected brand for a real spot, for the report
    # ground_truth[gate] = expected status; a gate absent from the dict is reported, not scored
    ground_truth: dict[str, str] = field(default_factory=dict)


REAL_EVAL = [
    ("Cheerios1960-0-30", "Cheerios"),
    ("chevrolet-31-61", "Chevrolet"),
    ("ivory_soap-25-55", "Ivory"),
    ("kodak_instamatic-31-60", "Kodak"),
    ("folgers-26-56", "Folgers"),
    ("labatts_beer-0-20", "Labatt's"),
    ("gilbert_slot_racers-0-30", "Gilbert"),
    ("MacleansToot-0-29", "Macleans"),
    ("ScottiesTiss-0-30", "Scotties"),
    ("GE_blender-0-30", "General Electric"),
]

# Every real spot: an unregistered trademark blocks rights, and a 1950s to 1960s film has no C2PA
# manifest, so provenance blocks too. Claim and brand have no ground truth on an unrelated real ad.
REAL_GROUND_TRUTH = {"rights": "BLOCK", "provenance": "BLOCK"}


def real_assets() -> list[AssetSpec]:
    specs = []
    for stem, brand in REAL_EVAL:
        specs.append(AssetSpec(
            asset_id=stem, kind="real",
            local=f"assets/real/eval/{stem}.mp4",
            gcs_uri=f"gs://{BUCKET}/real/eval/{stem}.mp4",
            brand=brand, ground_truth=dict(REAL_GROUND_TRUTH),
        ))
    return specs


def synthetic_assets() -> list[AssetSpec]:
    return [
        AssetSpec("nimbus-test-clip", "synthetic",
                  "assets/synthetic/nimbus-test-clip.mp4", f"gs://{BUCKET}/synthetic/nimbus-test-clip.mp4",
                  ground_truth={"rights": "PASS", "provenance": "PASS", "claim": "BLOCK", "brand": "PASS"}),
        AssetSpec("nimbus-clean-clip", "synthetic",
                  "assets/synthetic/calibration/nimbus-clean-clip.mp4", f"gs://{BUCKET}/calibration/nimbus-clean-clip.mp4",
                  ground_truth={"rights": "PASS", "provenance": "PASS", "claim": "PASS", "brand": "PASS"}),
        AssetSpec("nimbus-defect-brand-red", "synthetic",
                  "assets/synthetic/calibration/nimbus-defect-brand-red.mp4", f"gs://{BUCKET}/calibration/nimbus-defect-brand-red.mp4",
                  ground_truth={"brand": "BLOCK"}),
        AssetSpec("nimbus-defect-provenance-stripped", "synthetic",
                  "assets/synthetic/calibration/nimbus-defect-provenance-stripped.mp4", f"gs://{BUCKET}/calibration/nimbus-defect-provenance-stripped.mp4",
                  ground_truth={"provenance": "BLOCK"}),
        AssetSpec("nimbus-defect-provenance-broken", "synthetic",
                  "assets/synthetic/calibration/nimbus-defect-provenance-broken.mp4", f"gs://{BUCKET}/calibration/nimbus-defect-provenance-broken.mp4",
                  ground_truth={"provenance": "BLOCK"}),
        # Raw Veo output, unbranded and unsigned: no gcs_uri, it was never uploaded (only the six
        # named assets that already had one before this eval are used as-is).
        AssetSpec("veo-raw", "synthetic",
                  "assets/synthetic/veo-raw.mp4", None,
                  ground_truth={"rights": "PASS", "provenance": "BLOCK", "claim": "PASS", "brand": "BLOCK"}),
    ]


def all_assets() -> list[AssetSpec]:
    return real_assets() + synthetic_assets()


def run_one(spec: AssetSpec) -> dict:
    local = ROOT / spec.local
    gcs_uri = spec.gcs_uri
    if not local.exists():
        print(f"  ! {spec.asset_id}: local file missing at {local}, skipping", file=sys.stderr)
        return {"asset_id": spec.asset_id, "kind": spec.kind, "brand": spec.brand, "local_path": spec.local,
                "gcs_uri": gcs_uri, "ground_truth": spec.ground_truth, "error": "local file missing", "gates": {}}
    asset = Asset(asset_id=spec.asset_id, path=str(local), gcs_uri=gcs_uri)
    t0 = time.perf_counter()
    results: list[GateResult] = run_all(asset)
    wall_ms = int((time.perf_counter() - t0) * 1000)
    gates = {}
    for r in results:
        gates[r.gate] = {
            "status": r.status,
            "elapsed_ms": r.elapsed_ms,
            "reason": (r.reasons or [""])[0],
            "rule_ids": r.rule_ids,
            "usage": getattr(r, "usage", {}) or {},
        }
    return {"asset_id": spec.asset_id, "kind": spec.kind, "brand": spec.brand, "local_path": spec.local,
            "gcs_uri": gcs_uri, "ground_truth": spec.ground_truth, "wall_ms": wall_ms, "gates": gates}


def run_eval(specs: list[AssetSpec]) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    rows = []
    for i, spec in enumerate(specs, 1):
        print(f"[{i}/{len(specs)}] {spec.asset_id} ...", flush=True)
        t0 = time.perf_counter()
        row = run_one(spec)
        rows.append(row)
        for gate in GATES:
            g = row.get("gates", {}).get(gate)
            if g:
                print(f"    {gate:<11} {g['status']:<6} {g['elapsed_ms']:>7} ms  {g['reason'][:120]}", flush=True)
        print(f"    wall {int((time.perf_counter() - t0) * 1000):>7} ms", flush=True)
    finished = datetime.now(timezone.utc).isoformat()
    return {"started": started, "finished": finished, "bucket": BUCKET, "assets": rows}


# --- precision / recall and latency, over whatever ran (results.json need not be freshly produced) ---

def score(assets: list[dict]) -> dict[str, dict]:
    """For each gate: over the assets carrying a ground truth for it, precision, recall, and the
    confusion counts. BLOCK is the positive class (a gate exists to catch the bad case)."""
    out: dict[str, dict] = {}
    for gate in GATES:
        tp = fp = tn = fn = 0
        misses = []
        for a in assets:
            gt = a.get("ground_truth", {}).get(gate)
            g = a.get("gates", {}).get(gate)
            if gt is None or g is None:
                continue
            got = g["status"]
            if gt == "BLOCK" and got == "BLOCK":
                tp += 1
            elif gt == "BLOCK" and got != "BLOCK":
                fn += 1
                misses.append((a["asset_id"], gt, got))
            elif gt == "PASS" and got == "PASS":
                tn += 1
            elif gt == "PASS" and got != "PASS":
                fp += 1
                misses.append((a["asset_id"], gt, got))
        total = tp + fp + tn + fn
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        out[gate] = {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "n": total, "precision": precision,
                     "recall": recall, "misses": misses}
    return out


def latency(assets: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for gate in GATES:
        vals = [a["gates"][gate]["elapsed_ms"] for a in assets if gate in a.get("gates", {})]
        if not vals:
            out[gate] = {"n": 0, "median_ms": None, "max_ms": None}
            continue
        out[gate] = {"n": len(vals), "median_ms": int(statistics.median(vals)), "max_ms": max(vals)}
    return out


def fmt_pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def asset_cost_usd(asset: dict) -> float:
    """One asset's cost at list price: the sum of its four gates' usage.cost_usd."""
    return sum(float((g.get("usage") or {}).get("cost_usd") or 0) for g in asset.get("gates", {}).values())


def cost_summary(assets: list[dict]) -> dict:
    """Sum what airlock.cost.estimate put on every GateResult.usage: total list-price cost, total
    Video Intelligence minutes, and how many Gemini calls (claim plus brand, one each per asset)."""
    total_usd = 0.0
    video_minutes = 0.0
    gemini_calls = 0
    for a in assets:
        for gate, g in a.get("gates", {}).items():
            u = g.get("usage") or {}
            total_usd += float(u.get("cost_usd") or 0)
            video_minutes += float(u.get("video_minutes") or 0)
            if u.get("tokens_in") or u.get("tokens_out"):
                gemini_calls += 1
    return {"total_usd": round(total_usd, 4), "video_minutes": video_minutes, "gemini_calls": gemini_calls}


def write_eval_md(payload: dict) -> None:
    assets = payload["assets"]
    scores = score(assets)
    lat = latency(assets)
    lines: list[str] = []
    lines.append("# Gate evaluation: 10 real spots plus 6 synthetic assets")
    lines.append("")
    lines.append("Reproduce:")
    lines.append("")
    lines.append("```")
    lines.append("scripts/with_env.sh uv run python scripts/eval_gates.py")
    lines.append("```")
    lines.append("")
    lines.append(f"Run: {payload['started']} to {payload['finished']} (UTC). Bucket: `{payload['bucket']}`.")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| asset | kind | rights | claim | brand | provenance | wall | cost USD |")
    lines.append("|---|---|---|---|---|---|---|---|")
    per_asset_costs: list[float] = []
    for a in assets:
        if "error" in a:
            lines.append(f"| {a['asset_id']} | {a['kind']} | ERROR: {a['error']} | | | | | |")
            continue
        g = a["gates"]

        def cell(gate: str) -> str:
            r = g.get(gate)
            if not r:
                return ""
            return f"{r['status']} ({r['elapsed_ms']} ms)"

        wall = f"{a['wall_ms'] / 1000:.1f} s" if "wall_ms" in a else ""
        asset_cost = asset_cost_usd(a)
        per_asset_costs.append(asset_cost)
        lines.append(f"| {a['asset_id']} | {a['kind']} | {cell('rights')} | {cell('claim')} | {cell('brand')} | {cell('provenance')} | {wall} | ${asset_cost:.4f} |")
    lines.append("")
    lines.append("## Precision and recall, where a ground truth exists")
    lines.append("")
    lines.append("BLOCK is the positive class: a gate exists to catch the case it should block.")
    lines.append("")
    lines.append("| gate | n | tp | fp | tn | fn | precision | recall |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for gate in GATES:
        s = scores[gate]
        lines.append(f"| {gate} | {s['n']} | {s['tp']} | {s['fp']} | {s['tn']} | {s['fn']} | {fmt_pct(s['precision'])} | {fmt_pct(s['recall'])} |")
    lines.append("")
    any_miss = False
    for gate in GATES:
        for asset_id, gt, got in scores[gate]["misses"]:
            any_miss = True
            lines.append(f"- {gate} missed on `{asset_id}`: expected {gt}, got {got}")
    if not any_miss:
        lines.append("No misses against the stated ground truth.")
    lines.append("")
    lines.append("## Latency per gate")
    lines.append("")
    lines.append("| gate | n | median | max |")
    lines.append("|---|---|---|---|")
    for gate in GATES:
        lg = lat[gate]
        med = f"{lg['median_ms']} ms" if lg["median_ms"] is not None else "n/a"
        mx = f"{lg['max_ms']} ms" if lg["max_ms"] is not None else "n/a"
        lines.append(f"| {gate} | {lg['n']} | {med} | {mx} |")
    lines.append("")
    lines.append("## Cost, at list price")
    lines.append("")
    lines.append("From `pricing.yaml`, read from the Cloud Billing Catalog on 2026-08-29; the free")
    lines.append("monthly quotas are not netted out.")
    lines.append("")
    cost = cost_summary(assets)
    valid_costs = [x for x in per_asset_costs if x is not None]
    if valid_costs:
        median_cost = statistics.median(valid_costs)
        max_cost = max(valid_costs)
        lines.append(f"Median cost per asset: ${median_cost:.4f}. Maximum cost per asset: ${max_cost:.4f}.")
    lines.append(f"Total cost of the whole evaluation: ${cost['total_usd']:.4f}, "
                 f"{cost['video_minutes']:.0f} Video Intelligence minute(s), {cost['gemini_calls']} Gemini call(s).")
    lines.append("")
    lines.append("## What claim and brand found on the real spots, unscored")
    lines.append("")
    lines.append("These ten are real, unrelated commercials: there is no charter or substantiation")
    lines.append("file for them, so claim and brand cannot be right or wrong here, only informative.")
    lines.append("")
    for a in assets:
        if a["kind"] != "real" or "error" in a:
            continue
        g = a["gates"]
        claim_r = g.get("claim", {})
        brand_r = g.get("brand", {})
        lines.append(f"- `{a['asset_id']}` (expected brand {a['brand']}): claim {claim_r.get('status')}, "
                     f"\"{claim_r.get('reason', '')[:160]}\"; brand {brand_r.get('status')}, \"{brand_r.get('reason', '')[:160]}\"")
    lines.append("")
    EVAL_MD_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=None, help="comma-separated asset ids, default: all 16")
    ap.add_argument("--list", action="store_true", help="print the asset list and exit, run nothing")
    args = ap.parse_args()

    specs = all_assets()
    if args.list:
        for s in specs:
            print(f"{s.asset_id:<32} {s.kind:<10} {s.local:<45} {s.gcs_uri or '(no gcs uri)'}")
        return
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        specs = [s for s in specs if s.asset_id in wanted]
        missing = wanted - {s.asset_id for s in specs}
        if missing:
            sys.exit(f"unknown asset id(s): {sorted(missing)}")

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / "logs").mkdir(parents=True, exist_ok=True)
    payload = run_eval(specs)
    RESULTS_PATH.write_text(json.dumps(payload, indent=1))
    write_eval_md(payload)
    c = cost_summary(payload["assets"])
    print(f"cost estimate: ${c['total_usd']} at list price, {c['video_minutes']:.0f} Video Intelligence "
          f"minute(s), {c['gemini_calls']} Gemini call(s)")
    print(f"wrote {RESULTS_PATH} and {EVAL_MD_PATH}")


if __name__ == "__main__":
    main()
