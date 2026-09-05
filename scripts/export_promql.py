"""Export the verdict's PromQL to the console, so both read one source of truth.

The verdict (airlock/verdict.py, promql_questions) is the only place the questions are written.
The console used to carry its own TypeScript copy and it drifted (three questions where the verdict
asked four, no last_calibration_caught). This script writes console/src/lib/promql.json from the
Python function; the console imports that file; tests/test_promql_export.py fails when the
committed JSON no longer matches the export.

Run from the repo root after any change to promql_questions:

    uv run python scripts/export_promql.py            # rewrite console/src/lib/promql.json
    uv run python scripts/export_promql.py --check    # exit 1 when the committed file is stale

Generic on purpose: every key promql_questions returns is exported, per gate, in the order the
function returns them. One expression the console needs before a run and the verdict may stop
asking, seconds since the gate's last success, is added when the function no longer returns it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from airlock import verdict as verdict_module  # noqa: E402
from airlock.gates.base import GATES  # noqa: E402

OUTPUT = ROOT / "console" / "src" / "lib" / "promql.json"

# The console reads this before a run to say "idle: last success N ago". It is informational on
# the Python side; if promql_questions drops it the console still needs it, so it is written here.
HEALTH_ONLY_KEY = "seconds_since_success"


def seconds_since_success_expr(gate: str) -> str:
    window = getattr(verdict_module, "CALIBRATION_WINDOW", "7d")
    return f'time() - max(max_over_time(airlock_gate_last_success_ts{{gate="{gate}"}}[{window}]))'


def questions_for(gate: str) -> dict[str, str]:
    """Every PromQL expression the verdict asks for one gate, plus the health-only one when absent."""
    exprs = {str(k): str(v) for k, v in verdict_module.promql_questions(gate).items()}
    exprs.setdefault(HEALTH_ONLY_KEY, seconds_since_success_expr(gate))
    return exprs


def build() -> dict:
    gates = {gate: questions_for(gate) for gate in GATES}
    keys: list[str] = []
    for exprs in gates.values():
        for key in exprs:
            if key not in keys:
                keys.append(key)
    return {
        "source": "airlock/verdict.py promql_questions(gate), exported by scripts/export_promql.py; do not edit by hand",
        "keys": keys,
        "health_only_keys": [HEALTH_ONLY_KEY] if all(HEALTH_ONLY_KEY not in verdict_module.promql_questions(g) for g in GATES) else [],
        "stale_after_s": int(getattr(verdict_module, "STALE_AFTER_S", 900)),
        "gates": gates,
    }


def render(payload: dict) -> str:
    return json.dumps(payload, indent=2) + "\n"


def shown(path: Path) -> str:
    """The path relative to the repo when it is inside it, absolute otherwise."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare the committed file to a fresh export, exit 1 on a difference")
    parser.add_argument("--output", type=Path, default=OUTPUT, help=f"where to write (default {shown(OUTPUT)})")
    args = parser.parse_args(argv)

    fresh = render(build())
    if args.check:
        current = args.output.read_text() if args.output.exists() else ""
        if current == fresh:
            print(f"{shown(args.output)} matches airlock.verdict.promql_questions")
            return 0
        print(f"{shown(args.output)} is stale: run `uv run python scripts/export_promql.py`", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(fresh)
    payload = json.loads(fresh)
    print(f"wrote {shown(args.output)}: {len(payload['gates'])} gates x {len(payload['keys'])} expressions ({', '.join(payload['keys'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
