"""Run the deployed Agent Engine agent over REST and print every event, the pipeline stages readably.

Usage: python scripts/query_agent_engine.py <reasoning_engine_resource_name> [message] [--raw]
The message is a GCS URI or a JSON object such as {"gcs_uri": "...", "mute": ["rights"]}.
The console (M4) and the daily proof (airlock.daily_proof) use the same client, airlock.engine_client.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from airlock.engine_client import describe, stream_query  # noqa: E402


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    raw_mode = "--raw" in sys.argv
    if not args:
        sys.exit(__doc__)
    name = args[0]
    message = args[1] if len(args) > 1 else "run"
    t0 = time.time()
    try:
        for ev in stream_query(name, message):
            if ev.unparsed is not None:
                print(ev.unparsed[:200])
                continue
            if raw_mode or not ev.texts:
                if ev.error or raw_mode:
                    print(json.dumps({"author": ev.author, "text": ev.texts or None, "error": ev.error})[:400])
                continue
            for text in ev.texts:
                try:
                    print(describe(ev.author, json.loads(text), ev.t))
                except json.JSONDecodeError:
                    print(f"[{ev.t:6.1f}s] {ev.author:<16} {text[:200]}")
    except RuntimeError as exc:
        sys.exit(str(exc))
    print(f"done in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
