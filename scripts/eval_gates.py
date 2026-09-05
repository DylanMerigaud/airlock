"""Run the four gates on the eval set (10 real Prelinger excerpts plus 6 synthetic assets) and score
them against eval/manifest.yaml, per gate AND per rule id.

    scripts/with_env.sh uv run python scripts/eval_gates.py
    scripts/with_env.sh uv run python scripts/eval_gates.py --only nimbus-test-clip,veo-raw
    scripts/with_env.sh uv run python scripts/eval_gates.py --list
    uv run python scripts/eval_gates.py --rescore        # re-score eval/results.json, no cloud call

One asset at a time, so Video Intelligence never has two jobs running together. About 2 minutes
per asset (rights alone is 30 to 120 s on Video Intelligence); the whole set is about 16 Video
Intelligence minutes. Run the full set in the background with the log under eval/logs/:

    scripts/with_env.sh uv run python scripts/eval_gates.py > eval/logs/run-<timestamp>.log 2>&1 &

Ground truth (eval/manifest.yaml): per asset, the expected status per gate, the rule ids that must
fire (rules_expected) and the rule ids that must not fire (rules_forbidden), and for the real spots
the brand on screen and whether a person is on screen. A rule "fires" when the gate's status is
BLOCK and the id is in its rule_ids; the ids a PASS lists are the rules it checked and satisfied.
A forbidden rule that fires is a false positive; an expected rule that does not fire is a miss.

Writes eval/results.json (every gate result per asset: status, elapsed_ms, reasons, rule_ids,
usage, what the gate found, and the ground truth it is scored against) and eval/EVAL.md (the
tables: per gate, per rule, brand identification, latency, cost, surprises). Every percentage is
printed beside the count it is made of. AIRLOCK_RUNTIME=eval is set in-process, so the telemetry
Grafana sees is labelled and does not read as a normal console or calibration run.

Fetch the assets first: scripts/fetch_assets.sh (the excerpts are cut from archive.org and hash
checked; the synthetic clips come from the GitHub release).

results.json is rewritten after every asset, and --only replaces just those assets' rows in the
existing file (the other rows stay, with the run's earlier start time), so a run cut short or a
re-run of one asset never loses the rest. A watchdog (AIRLOCK_EVAL_ASSET_BUDGET_S, default 1200 s
per asset) turns a gate that hangs into a recorded ERROR: on 2026-09-05 the first run of the day
hung for 32 minutes on veo-raw inside a Gemini call whose HTTP client has no timeout
(google-genai leaves httpx at timeout=None), where the Video Intelligence call at least has one.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import signal
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from airlock.gates.base import GATES, Asset, GateResult  # noqa: E402

BUCKET = os.environ.get("AIRLOCK_ASSETS_BUCKET", "airlock-agentic-cinema-assets")
EVAL_DIR = ROOT / "eval"
MANIFEST_PATH = EVAL_DIR / "manifest.yaml"
RESULTS_PATH = EVAL_DIR / "results.json"
EVAL_MD_PATH = EVAL_DIR / "EVAL.md"
GATES_DIR = ROOT / "airlock" / "gates"
ASSET_BUDGET_S = float(os.environ.get("AIRLOCK_EVAL_ASSET_BUDGET_S", "1200"))

# Surprises from earlier runs of this eval, kept so a re-run that no longer shows them still
# records that they happened (date, asset, what was seen). The current run's own surprises are
# derived from the data below and printed above these.
EARLIER_SURPRISES = [
    ("2026-08-29", "kodak_instamatic-31-60",
     "the rights gate cited registry:explicit_content on a 1963 family party scene (a false positive the "
     "status-level score of that day counted as a correct BLOCK)"),
    ("2026-08-29", "6 of 10 real spots",
     "Video Intelligence named the wrong company at high confidence (a 1955 Chevrolet read as DeLorean Motor "
     "Company; Ichiran, Peugeot, Vauxhall, Lucid and Target on five others); the BLOCK held because the policy "
     "blocks any brand the registry does not know, so the status-level score hid it"),
]


@dataclass(frozen=True)
class AssetSpec:
    asset_id: str
    kind: str  # "real" or "synthetic"
    local: str  # path relative to ROOT
    gcs_uri: str | None
    brand: str | None = None  # the brand on screen, for a real spot
    brand_names: tuple[str, ...] = ()  # names the rights gate may report for that brand
    faces: bool | None = None  # a person on screen (real spots, hand-labelled)
    faces_note: str = ""
    # status[gate] = expected status; a gate absent from the dict is reported, not scored
    status: dict[str, str] = field(default_factory=dict)
    rules_expected: dict[str, list[str]] = field(default_factory=dict)
    rules_forbidden: dict[str, list[str]] = field(default_factory=dict)

    def ground_truth(self) -> dict[str, Any]:
        """What results.json carries per asset so the scoring can run on the file alone."""
        return {"status": dict(self.status), "rules_expected": {g: list(v) for g, v in self.rules_expected.items()},
                "rules_forbidden": {g: list(v) for g, v in self.rules_forbidden.items()},
                "brand_names": list(self.brand_names), "faces": self.faces, "faces_note": self.faces_note}


# --- the manifest ---

def _merge_rules(shared: dict[str, list[str]] | None, own: dict[str, list[str]] | None) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {g: list(v) for g, v in (shared or {}).items()}
    for g, v in (own or {}).items():
        out.setdefault(g, [])
        out[g].extend(x for x in v if x not in out[g])
    return out


def load_manifest(path: pathlib.Path = MANIFEST_PATH, bucket: str = BUCKET) -> list[AssetSpec]:
    """The 16 assets and their ground truth. Real spots share real_rules and add the faces rule
    from their hand label; synthetic assets carry everything explicitly."""
    doc = yaml.safe_load(path.read_text()) or {}
    shared = doc.get("real_rules") or {}
    specs: list[AssetSpec] = []
    for row in doc.get("real") or []:
        expected = _merge_rules(shared.get("rules_expected"), row.get("rules_expected"))
        forbidden = _merge_rules(shared.get("rules_forbidden"), row.get("rules_forbidden"))
        faces = row.get("faces")
        if faces is True:
            expected.setdefault("rights", []).append("registry:faces:no_release")
        elif faces is False:
            forbidden.setdefault("rights", []).append("registry:faces:no_release")
        specs.append(AssetSpec(
            asset_id=row["asset_id"], kind="real",
            local=row.get("local") or f"assets/real/eval/{row['asset_id']}.mp4",
            gcs_uri=(row.get("gcs_uri") or f"gs://{{bucket}}/real/eval/{row['asset_id']}.mp4").replace("{bucket}", bucket),
            brand=row.get("brand"), brand_names=tuple(row.get("brand_names") or ()),
            faces=faces, faces_note=row.get("faces_note", ""),
            status=dict(shared.get("status") or {}) | dict(row.get("status") or {}),
            rules_expected=expected, rules_forbidden=forbidden,
        ))
    for row in doc.get("synthetic") or []:
        gcs = row.get("gcs_uri")
        specs.append(AssetSpec(
            asset_id=row["asset_id"], kind="synthetic", local=row["local"],
            gcs_uri=gcs.replace("{bucket}", bucket) if gcs else None,
            status=dict(row.get("status") or {}),
            rules_expected={g: list(v) for g, v in (row.get("rules_expected") or {}).items()},
            rules_forbidden={g: list(v) for g, v in (row.get("rules_forbidden") or {}).items()},
        ))
    return specs


def known_rule_ids(gates_dir: pathlib.Path = GATES_DIR) -> set[str]:
    """Every rule id the gates can put in rule_ids, read from their source: the registry and
    charter literals, the provenance constants, and the claim table's FTC and ASA citations."""
    ids: set[str] = set()
    for p in gates_dir.glob("*.py"):
        src = p.read_text()
        ids.update(re.findall(r'"((?:registry|charter|airlock):[a-z_:-]+)"', src))
    from airlock.gates import claim  # noqa: PLC0415  (the gate modules do no I/O at import)
    for rule in claim.RULES.values():
        ids.update(rule["us"])
        ids.update(rule["uk"])
    ids.update(claim.PASS_RULE_IDS)  # the ids a claim PASS lists
    return ids


def manifest_rule_ids(specs: list[AssetSpec]) -> set[str]:
    ids: set[str] = set()
    for s in specs:
        for table in (s.rules_expected, s.rules_forbidden):
            for v in table.values():
                ids.update(v)
    return ids


# --- running ---

def summarize_evidence(gate: str, result: GateResult) -> dict[str, Any]:
    """What the gate found, small enough for results.json: the brand names the rights gate saw
    and how, the face tracks and explicit frames; the claims the claim gate blocked on; the
    brand gate's findings; the provenance signer line."""
    ev = result.evidence[0] if result.evidence else {}
    if gate == "rights":
        findings = ev.get("findings") or []
        return {
            "brands": [{"name": f.get("name"), "how": f.get("how"), "status": f.get("status"), "first_seen_s": f.get("first_seen_s"),
                        "confidence": f.get("confidence")} for f in findings if f.get("element") == "brand"],
            "face_tracks": ev.get("face_tracks", 0),
            "explicit_frames": ev.get("explicit_frames") or {},
            "text_lines": ev.get("text_lines", 0),
        }
    if gate == "claim":
        return {"claims_total": ev.get("claims_total", 0),
                "blocking": [{"quote": c.get("quote"), "kind": c.get("kind"), "start_s": c.get("start_s")} for c in ev.get("blocking_claims") or []],
                "advisory": len(ev.get("advisory_claims") or [])}
    if gate == "brand":
        return {"wordmark_seen": ev.get("wordmark_seen"), "other_brands_seen": ev.get("other_brands_seen") or [],
                "dominant_colors_hex": ev.get("dominant_colors_hex") or [], "exclusion_violations": len(ev.get("exclusion_violations") or [])}
    if gate == "provenance":
        if "manifest" in ev and not ev.get("manifest"):
            return {"manifest": None}
        return {k: ev.get(k) for k in ("validation_state", "issuer", "claim_generator", "failure_codes", "assertions") if k in ev}
    return {}


class asset_watchdog:
    """SIGALRM after ASSET_BUDGET_S: the alarm raises TimeoutError in the main thread, inside
    whatever gate is running, and run_gate records it as that gate's ERROR (an instrument that
    hangs is an instrument that failed). Disarmed on exit; a no-op when the budget is 0."""

    def __init__(self, asset_id: str, budget_s: float = ASSET_BUDGET_S):
        self.asset_id = asset_id
        self.budget_s = budget_s
        self._previous = None

    def _fire(self, signum, frame):  # noqa: ARG002
        raise TimeoutError(f"eval watchdog: {self.asset_id} exceeded {self.budget_s:.0f} s (AIRLOCK_EVAL_ASSET_BUDGET_S)")

    def __enter__(self):
        if self.budget_s > 0:
            self._previous = signal.signal(signal.SIGALRM, self._fire)
            signal.alarm(int(self.budget_s))
        return self

    def __exit__(self, *exc):
        if self.budget_s > 0:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, self._previous)
        return False


def run_one(spec: AssetSpec) -> dict:
    from airlock.run import run_all  # noqa: PLC0415  (imports the gate modules and their cloud clients)

    base = {"asset_id": spec.asset_id, "kind": spec.kind, "brand": spec.brand, "local_path": spec.local,
            "gcs_uri": spec.gcs_uri, "ground_truth": spec.ground_truth()}
    local = ROOT / spec.local
    if not local.exists():
        print(f"  ! {spec.asset_id}: local file missing at {local}, skipping (scripts/fetch_assets.sh)", file=sys.stderr)
        return base | {"error": "local file missing", "gates": {}}
    asset = Asset(asset_id=spec.asset_id, path=str(local), gcs_uri=spec.gcs_uri)
    t0 = time.perf_counter()
    with asset_watchdog(spec.asset_id):
        results: list[GateResult] = run_all(asset)
    wall_ms = int((time.perf_counter() - t0) * 1000)
    gates = {}
    for r in results:
        gates[r.gate] = {
            "status": r.status,
            "elapsed_ms": r.elapsed_ms,
            "reason": (r.reasons or [""])[0],
            "reasons": list(r.reasons),
            "rule_ids": list(r.rule_ids),
            "usage": dict(r.usage or {}),
            "found": summarize_evidence(r.gate, r),
        }
    return base | {"wall_ms": wall_ms, "gates": gates}


def code_version() -> str:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def merge_rows(previous: list[dict], fresh: list[dict], order: list[str]) -> list[dict]:
    """The fresh rows replace the previous rows of the same asset; everything else stays, in
    manifest order (unknown ids last, in their old order)."""
    by_id = {r["asset_id"]: r for r in previous}
    by_id.update({r["asset_id"]: r for r in fresh})
    rank = {asset_id: i for i, asset_id in enumerate(order)}
    return [by_id[k] for k in sorted(by_id, key=lambda k: (rank.get(k, len(order)), k))]


def run_eval(specs: list[AssetSpec], previous: dict | None = None, order: list[str] | None = None,
             checkpoint: pathlib.Path | None = RESULTS_PATH) -> dict:
    """Run the specs one at a time. After every asset the payload so far is merged into
    `previous` (the results.json on disk, when there is one) and written to `checkpoint`."""
    started = (previous or {}).get("started") or datetime.now(UTC).isoformat()
    prev_rows = list((previous or {}).get("assets") or [])
    order = order or [s.asset_id for s in specs]
    rows: list[dict] = []
    payload: dict = {}
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
        payload = {"started": started,
                   "finished": datetime.now(UTC).isoformat(), "bucket": BUCKET, "code": code_version(),
                   "manifest": str(MANIFEST_PATH.relative_to(ROOT)), "assets": merge_rows(prev_rows, rows, order),
                   "partial": i < len(specs)}
        if checkpoint is not None:
            checkpoint.write_text(json.dumps(payload, indent=1))
    if not payload:
        payload = {"started": started, "finished": started, "bucket": BUCKET, "code": code_version(),
                   "manifest": str(MANIFEST_PATH.relative_to(ROOT)), "assets": prev_rows, "partial": False}
    return payload


# --- scoring, over whatever ran (results.json need not be freshly produced) ---

def fired(gate_row: dict | None) -> set[str]:
    """The rule ids a gate result counts as fired: its rule_ids when it BLOCKed, nothing otherwise."""
    if not gate_row or gate_row.get("status") != "BLOCK":
        return set()
    return set(gate_row.get("rule_ids") or [])


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def score_status(assets: list[dict]) -> dict[str, dict]:
    """Per gate, over the assets carrying an expected status for it: precision, recall and the
    confusion counts. BLOCK is the positive class (a gate exists to catch the bad case)."""
    out: dict[str, dict] = {}
    for gate in GATES:
        tp = fp = tn = fn = 0
        misses = []
        for a in assets:
            gt = (a.get("ground_truth") or {}).get("status", {}).get(gate)
            g = (a.get("gates") or {}).get(gate)
            if gt is None or g is None:
                continue
            got = g["status"]
            if gt == "BLOCK" and got == "BLOCK":
                tp += 1
            elif gt == "BLOCK":
                fn += 1
                misses.append((a["asset_id"], gt, got))
            elif gt == "PASS" and got == "PASS":
                tn += 1
            else:
                fp += 1
                misses.append((a["asset_id"], gt, got))
        out[gate] = {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "n": tp + fp + tn + fn,
                     "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn), "misses": misses}
    return out


# A word the gate's reason for that rule carries, to quote the right line when a rule fires where
# it must not (the gates write one reason per finding, in no fixed order).
RULE_REASON_WORD = {
    "registry:explicit_content": "explicit content", "registry:faces:no_release": "face track",
    "registry:brands:unknown": "does not know", "registry:brands:not_cleared": "not_cleared",
    "charter:palette": "palette", "charter:tone": "tone", "charter:exclusions": "exclusion",
    "charter:mandatory_mentions": "mandatory mention", "charter:typography": "longer than",
}


def reason_for(rule: str, gate_row: dict | None) -> str:
    """The reason line the gate wrote for this rule, else its first reason."""
    reasons = list((gate_row or {}).get("reasons") or [])
    word = RULE_REASON_WORD.get(rule)
    if word:
        for r in reasons:
            if word in r:
                return r
    return reasons[0] if reasons else (gate_row or {}).get("reason", "")


def score_rules(assets: list[dict]) -> dict[str, dict]:
    """Per rule id, over the (asset, gate) pairs where the manifest says the rule must fire or
    must not: tp (expected, fired), fn (expected, silent), fp (forbidden, fired), tn (forbidden,
    silent). A gate that did not run (ERROR or absent) counts as silent."""
    out: dict[str, dict] = {}
    for a in assets:
        gt = a.get("ground_truth") or {}
        for gate in GATES:
            g = (a.get("gates") or {}).get(gate)
            got = fired(g)
            for rule in gt.get("rules_expected", {}).get(gate, []):
                row = out.setdefault(rule, {"gate": gate, "tp": 0, "fp": 0, "tn": 0, "fn": 0, "false_positives": [], "misses": []})
                if rule in got:
                    row["tp"] += 1
                else:
                    row["fn"] += 1
                    row["misses"].append((a["asset_id"], (g or {}).get("status", "absent")))
            for rule in gt.get("rules_forbidden", {}).get(gate, []):
                row = out.setdefault(rule, {"gate": gate, "tp": 0, "fp": 0, "tn": 0, "fn": 0, "false_positives": [], "misses": []})
                if rule in got:
                    row["fp"] += 1
                    row["false_positives"].append((a["asset_id"], reason_for(rule, g)))
                else:
                    row["tn"] += 1
    for row in out.values():
        row["n"] = row["tp"] + row["fp"] + row["tn"] + row["fn"]
        row["precision"] = _ratio(row["tp"], row["tp"] + row["fp"])
        row["recall"] = _ratio(row["tp"], row["tp"] + row["fn"])
    return out


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", s.lower()) if t}


def brand_named(expected_names: list[str], seen_names: list[str]) -> bool:
    """True when one of the names the gate reported shares every token of one accepted name
    ("General Electric Company" names General Electric; "GE" names GE; "DeLorean" does not name
    Chevrolet)."""
    for want in expected_names:
        wt = _tokens(want)
        if not wt:
            continue
        for seen in seen_names:
            if wt <= _tokens(seen):
                return True
    return False


def score_brand_names(assets: list[dict]) -> dict:
    """On the real spots: did the rights gate name the brand that is on screen? The BLOCK does
    not depend on it (any unknown brand blocks); a rights desk does."""
    rows = []
    for a in assets:
        gt = a.get("ground_truth") or {}
        names = gt.get("brand_names") or []
        g = (a.get("gates") or {}).get("rights")
        if not names or not g:
            continue
        seen = [b.get("name") or "" for b in (g.get("found") or {}).get("brands") or []]
        rows.append({"asset_id": a["asset_id"], "expected": names, "seen": seen, "named": brand_named(names, seen)})
    named = sum(1 for r in rows if r["named"])
    return {"n": len(rows), "named": named, "ratio": _ratio(named, len(rows)), "rows": rows}


def latency(assets: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for gate in GATES:
        vals = [g["elapsed_ms"] for a in assets for g in [(a.get("gates") or {}).get(gate)] if g and g.get("elapsed_ms") is not None]
        if not vals:
            out[gate] = {"n": 0, "median_ms": None, "max_ms": None}
            continue
        out[gate] = {"n": len(vals), "median_ms": int(statistics.median(vals)), "max_ms": max(vals)}
    return out


def fmt_pct(x: float | None, num: int | None = None, den: int | None = None) -> str:
    """A percentage never travels alone: '100% (10 of 10)'."""
    if x is None:
        return "n/a (0 of 0)"
    return f"{x * 100:.0f}% ({num} of {den})"


def asset_cost_usd(asset: dict) -> float:
    """One asset's cost at list price: the sum of its four gates' usage.cost_usd."""
    return sum(float((g.get("usage") or {}).get("cost_usd") or 0) for g in (asset.get("gates") or {}).values())


def cost_summary(assets: list[dict]) -> dict:
    """Sum what airlock.cost.estimate put on every GateResult.usage: total list-price cost, total
    Video Intelligence minutes, and how many Gemini calls (claim plus brand, one each per asset)."""
    total_usd = 0.0
    video_minutes = 0.0
    gemini_calls = 0
    for a in assets:
        for g in (a.get("gates") or {}).values():
            u = g.get("usage") or {}
            total_usd += float(u.get("cost_usd") or 0)
            video_minutes += float(u.get("video_minutes") or 0)
            if u.get("tokens_in") or u.get("tokens_out"):
                gemini_calls += 1
    return {"total_usd": round(total_usd, 4), "video_minutes": video_minutes, "gemini_calls": gemini_calls}


def surprises(assets: list[dict]) -> list[str]:
    """What this run shows that the status-level score would hide: forbidden rules that fired,
    expected rules that stayed silent, brands Video Intelligence misnamed, gates in ERROR."""
    out: list[str] = []
    rules = score_rules(assets)
    for rule in sorted(rules, key=lambda r: (rules[r]["gate"], r)):
        for asset_id, reason in rules[rule]["false_positives"]:
            out.append(f"`{rule}` fired on `{asset_id}` where it must not: \"{reason[:200]}\"")
        for asset_id, status in rules[rule]["misses"]:
            out.append(f"`{rule}` did not fire on `{asset_id}` where it must (gate status {status})")
    names = score_brand_names(assets)
    wrong = [r for r in names["rows"] if not r["named"]]
    if wrong:
        out.append(f"Video Intelligence did not name the brand on {len(wrong)} of {names['n']} real spots: "
                   + "; ".join(f"`{r['asset_id']}` expected {' or '.join(r['expected'])}, got {', '.join(r['seen']) or 'no brand'}" for r in wrong))
    for a in assets:
        if "error" in a:
            out.append(f"`{a['asset_id']}` did not run: {a['error']}")
        for gate, g in (a.get("gates") or {}).items():
            if g.get("status") == "ERROR":
                out.append(f"`{gate}` on `{a['asset_id']}` ended in ERROR: \"{g.get('reason', '')[:200]}\"")
    return out


def score_all(payload: dict) -> dict:
    assets = payload["assets"]
    return {"status": score_status(assets), "rules": score_rules(assets), "brand_names": score_brand_names(assets),
            "latency": latency(assets), "cost": cost_summary(assets), "surprises": surprises(assets)}


# --- the report ---

def write_eval_md(payload: dict) -> None:
    assets = payload["assets"]
    scores = score_status(assets)
    rules = score_rules(assets)
    names = score_brand_names(assets)
    lat = latency(assets)
    n_real = sum(1 for a in assets if a.get("kind") == "real")
    n_synth = sum(1 for a in assets if a.get("kind") == "synthetic")
    lines: list[str] = []
    lines.append(f"# Gate evaluation: {n_real} real spots plus {n_synth} synthetic assets")
    lines.append("")
    lines.append("Reproduce (the excerpts are cut from archive.org by `scripts/fetch_assets.sh` and hash checked):")
    lines.append("")
    lines.append("```")
    lines.append("scripts/fetch_assets.sh")
    lines.append("scripts/with_env.sh uv run python scripts/eval_gates.py")
    lines.append("```")
    lines.append("")
    lines.append(f"Run: {payload['started']} to {payload['finished']} (UTC), code `{payload.get('code', 'unknown')}`, "
                 f"ground truth `{payload.get('manifest', 'eval/manifest.yaml')}`. Bucket: `{payload['bucket']}`."
                 + (" PARTIAL: the run that wrote this was cut before its last asset." if payload.get("partial") else ""))
    lines.append("")
    lines.append("Every percentage is printed beside the count it is made of. BLOCK is the positive class: a")
    lines.append("gate exists to catch the case it should block. A rule fires when its gate BLOCKs citing it;")
    lines.append("a forbidden rule that fires is a false positive even when the BLOCK itself was right.")
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

        def cell(gate: str, g: dict = g) -> str:
            r = g.get(gate)
            if not r:
                return ""
            return f"{r['status']} ({r.get('elapsed_ms', 0)} ms)"

        wall = f"{a['wall_ms'] / 1000:.1f} s" if "wall_ms" in a else ""
        asset_cost = asset_cost_usd(a)
        per_asset_costs.append(asset_cost)
        lines.append(f"| {a['asset_id']} | {a['kind']} | {cell('rights')} | {cell('claim')} | {cell('brand')} | {cell('provenance')} "
                     f"| {wall} | ${asset_cost:.4f} |")
    lines.append("")
    lines.append("## Per gate: the status against the expected status")
    lines.append("")
    lines.append("| gate | n | tp | fp | tn | fn | precision | recall |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for gate in GATES:
        s = scores[gate]
        lines.append(f"| {gate} | {s['n']} | {s['tp']} | {s['fp']} | {s['tn']} | {s['fn']} | "
                     f"{fmt_pct(s['precision'], s['tp'], s['tp'] + s['fp'])} | {fmt_pct(s['recall'], s['tp'], s['tp'] + s['fn'])} |")
    lines.append("")
    status_misses = [(gate, *m) for gate in GATES for m in scores[gate]["misses"]]
    if status_misses:
        for gate, asset_id, gt, got in status_misses:
            lines.append(f"- {gate} on `{asset_id}`: expected {gt}, got {got}")
    else:
        lines.append("No status miss against the manifest.")
    lines.append("")
    lines.append("## Per rule: did the rule fire where it must, and stay silent where it must not")
    lines.append("")
    lines.append("n is the number of assets the manifest says something about for that rule (expected or")
    lines.append("forbidden). tp: expected and fired. fn: expected and silent. fp: forbidden and fired. tn:")
    lines.append("forbidden and silent. A rule with no forbidden case has no precision denominator beyond its")
    lines.append("own true positives; a rule with no expected case has no recall.")
    lines.append("")
    lines.append("| rule | gate | n | tp | fp | tn | fn | precision | recall |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for rule in sorted(rules, key=lambda r: (GATES.index(rules[r]["gate"]), r)):
        s = rules[rule]
        lines.append(f"| `{rule}` | {s['gate']} | {s['n']} | {s['tp']} | {s['fp']} | {s['tn']} | {s['fn']} | "
                     f"{fmt_pct(s['precision'], s['tp'], s['tp'] + s['fp'])} | {fmt_pct(s['recall'], s['tp'], s['tp'] + s['fn'])} |")
    lines.append("")
    rule_events = [(rule, s) for rule, s in rules.items() if s["false_positives"] or s["misses"]]
    if rule_events:
        for rule, s in sorted(rule_events, key=lambda x: (GATES.index(x[1]["gate"]), x[0])):
            for asset_id, reason in s["false_positives"]:
                lines.append(f"- false positive: `{rule}` fired on `{asset_id}`: \"{reason[:200]}\"")
            for asset_id, status in s["misses"]:
                lines.append(f"- miss: `{rule}` did not fire on `{asset_id}` (gate status {status})")
    else:
        lines.append("No rule fired where it must not, none stayed silent where it must fire.")
    lines.append("")
    lines.append("## Brand identification on the real spots, scored apart from the BLOCK")
    lines.append("")
    lines.append("The BLOCK on a real spot does not depend on the name (any brand the registry does not know")
    lines.append("blocks); a rights desk needs the name. Named means one name the gate reported carries every")
    lines.append("token of the brand on screen, as hand-labelled in the manifest.")
    lines.append("")
    lines.append(f"Brand named: {fmt_pct(names['ratio'], names['named'], names['n'])}.")
    lines.append("")
    lines.append("| asset | brand on screen | what the rights gate reported | named |")
    lines.append("|---|---|---|---|")
    for r in names["rows"]:
        lines.append(f"| {r['asset_id']} | {' or '.join(r['expected'])} | {', '.join(r['seen']) or 'no brand'} | {'yes' if r['named'] else 'no'} |")
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
    if per_asset_costs:
        lines.append(f"Median cost per asset: ${statistics.median(per_asset_costs):.4f} (n={len(per_asset_costs)}). "
                     f"Maximum cost per asset: ${max(per_asset_costs):.4f}.")
    lines.append(f"Total cost of the whole evaluation: ${cost['total_usd']:.4f}, "
                 f"{cost['video_minutes']:.0f} Video Intelligence minute(s), {cost['gemini_calls']} Gemini call(s).")
    lines.append("")
    lines.append("## Surprises")
    lines.append("")
    lines.append("What the status-level score would hide. This run:")
    lines.append("")
    run_surprises = surprises(assets)
    if run_surprises:
        lines.extend(f"- {s}" for s in run_surprises)
    else:
        lines.append("- none: every expected rule fired, no forbidden rule fired, every brand named, no ERROR.")
    lines.append("")
    lines.append("Seen in earlier runs of this eval, kept for the record:")
    lines.append("")
    lines.extend(f"- {date}, `{where}`: {what}" for date, where, what in EARLIER_SURPRISES)
    lines.append("")
    lines.append("## What claim and brand found on the real spots, unscored")
    lines.append("")
    lines.append("These ten are real, unrelated commercials: there is no charter or substantiation")
    lines.append("file for them, so claim and brand cannot be right or wrong here, only informative.")
    lines.append("")
    for a in assets:
        if a.get("kind") != "real" or "error" in a:
            continue
        g = a["gates"]
        claim_r = g.get("claim", {})
        brand_r = g.get("brand", {})
        lines.append(f"- `{a['asset_id']}` (brand on screen {a.get('brand')}): claim {claim_r.get('status')}, "
                     f"\"{claim_r.get('reason', '')[:160]}\"; brand {brand_r.get('status')}, \"{brand_r.get('reason', '')[:160]}\"")
    lines.append("")
    EVAL_MD_PATH.write_text("\n".join(lines) + "\n")


def print_summary(payload: dict) -> None:
    assets = payload["assets"]
    print("per gate (status):")
    for gate, s in score_status(assets).items():
        print(f"  {gate:<11} n={s['n']:<3} precision {fmt_pct(s['precision'], s['tp'], s['tp'] + s['fp'])}  "
              f"recall {fmt_pct(s['recall'], s['tp'], s['tp'] + s['fn'])}")
    print("per rule:")
    rules = score_rules(assets)
    for rule in sorted(rules, key=lambda r: (GATES.index(rules[r]["gate"]), r)):
        s = rules[rule]
        print(f"  {rule:<42} {s['gate']:<11} n={s['n']:<3} precision {fmt_pct(s['precision'], s['tp'], s['tp'] + s['fp'])}  "
              f"recall {fmt_pct(s['recall'], s['tp'], s['tp'] + s['fn'])}")
    names = score_brand_names(assets)
    print(f"brand named on the real spots: {fmt_pct(names['ratio'], names['named'], names['n'])}")
    c = cost_summary(assets)
    print(f"cost estimate: ${c['total_usd']} at list price, {c['video_minutes']:.0f} Video Intelligence "
          f"minute(s), {c['gemini_calls']} Gemini call(s)")
    for s in surprises(assets):
        print(f"surprise: {s}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=None, help="comma-separated asset ids, default: all 16")
    ap.add_argument("--list", action="store_true", help="print the asset list and its ground truth, run nothing")
    ap.add_argument("--rescore", action="store_true", help="re-score eval/results.json and rewrite eval/EVAL.md, no cloud call")
    args = ap.parse_args()

    if args.rescore:
        payload = json.loads(RESULTS_PATH.read_text())
        write_eval_md(payload)
        print_summary(payload)
        print(f"rewrote {EVAL_MD_PATH} from {RESULTS_PATH}")
        return

    specs = load_manifest()
    unknown = manifest_rule_ids(specs) - known_rule_ids()
    if unknown:
        sys.exit(f"rule id(s) in {MANIFEST_PATH} that no gate emits (fix the manifest): {sorted(unknown)}")
    if args.list:
        for s in specs:
            print(f"{s.asset_id:<32} {s.kind:<10} {s.local:<50} {s.gcs_uri or '(no gcs uri)'}")
            print(f"{'':<32} status {json.dumps(s.status)}")
            print(f"{'':<32} expected {json.dumps(s.rules_expected)}")
            print(f"{'':<32} forbidden {json.dumps(s.rules_forbidden)}")
        return
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        specs = [s for s in specs if s.asset_id in wanted]
        missing = wanted - {s.asset_id for s in specs}
        if missing:
            sys.exit(f"unknown asset id(s): {sorted(missing)}")

    os.environ["AIRLOCK_RUNTIME"] = "eval"
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / "logs").mkdir(parents=True, exist_ok=True)
    previous = None
    if args.only and RESULTS_PATH.exists():
        previous = json.loads(RESULTS_PATH.read_text())
        if previous.get("manifest") is None:
            previous = None  # a results.json from before the manifest carries no per-rule ground truth: start over
    payload = run_eval(specs, previous=previous, order=[s.asset_id for s in load_manifest()])
    RESULTS_PATH.write_text(json.dumps(payload, indent=1))
    write_eval_md(payload)
    print_summary(payload)
    print(f"wrote {RESULTS_PATH} and {EVAL_MD_PATH}")


if __name__ == "__main__":
    main()
