"""Record a console fixture: one pipeline run through the deployed Agent Engine, written as the JSONL the
console replays in mock mode (one {"author", "text"} line per text part, in arrival order).

    uv run python scripts/record_fixture.py <message> <fixture path>
    uv run python scripts/record_fixture.py gs://airlock-agentic-cinema-assets/calibration/nimbus-clean-clip.mp4 console/fixtures/run-clean-pass.jsonl
    uv run python scripts/record_fixture.py '{"gcs_uri": "gs://.../nimbus-clean-clip.mp4", "fault": {"rights": "timeout"}}' console/fixtures/run-nimbus-instrument-error.jsonl

The engine comes from AGENT_ENGINE_RESOURCE (airlock.settings). The recording is the real run: it pushes
telemetry, writes an annotation and, when the verdict needs a human, opens or joins an incident.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

from airlock.engine_client import describe, resource_from_env, stream_query


def main() -> int:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    message, out = sys.argv[1], pathlib.Path(sys.argv[2])
    name = resource_from_env()
    t0 = time.time()
    lines: list[str] = []
    for ev in stream_query(name, message):
        if ev.unparsed is not None or not ev.texts:
            continue
        for text in ev.texts:
            lines.append(json.dumps({"author": ev.author, "text": text}))
            try:
                print(describe(ev.author, json.loads(text), ev.t))
            except json.JSONDecodeError:
                print(f"[{ev.t:6.1f}s] {ev.author:<16} {text[:160]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out} ({len(lines)} lines) in {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
