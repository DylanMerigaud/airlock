"""Run the deployed Agent Engine agent over REST and print every event, the pipeline stages readably.

Usage: python scripts/query_agent_engine.py <reasoning_engine_resource_name> [message] [--raw]
The message is a GCS URI or a JSON object such as {"gcs_uri": "...", "mute": ["rights"]}.
The console (M4) uses the same :streamQuery endpoint.
"""

from __future__ import annotations

import json
import sys
import time
import uuid

import google.auth
import google.auth.transport.requests
import httpx


def describe(author: str, d: dict, t: float) -> str:
    st = d.get("stage")
    if st == "running":
        return f"[{t:6.1f}s] {author:<16} running  {d.get('gate')}" + ("  (telemetry muted)" if d.get("telemetry_muted") else "")
    if st == "done":
        return f"[{t:6.1f}s] {author:<16} {d.get('status'):<6} {d.get('elapsed_ms', 0):>6} ms  {(d.get('reasons') or [''])[0][:140]}"
    if st == "grafana":
        vals = {k: v.get("value") for k, v in (d.get("answers") or {}).items()}
        return f"[{t:6.1f}s] {author:<16} grafana  {d.get('gate'):<11} {d.get('health')}; {d.get('calibration')}  {vals}"
    if st == "verdict":
        head = f"[{t:6.1f}s] {author:<16} VERDICT {d.get('status')} ({d.get('motive')}) needs_human={d.get('needs_human')} annotation={d.get('annotation_id')} {d.get('elapsed_ms')} ms"
        return head + "".join(f"\n{'':>26}{r[:200]}" for r in d.get("reasons", []))
    if st == "escalation":
        if d.get("opened"):
            return f"[{t:6.1f}s] {author:<16} INCIDENT {d.get('incident_id')} {d.get('incident_url')}"
        if d.get("fallback"):
            return f"[{t:6.1f}s] {author:<16} FALLBACK needs-human annotation {d.get('fallback_annotation_id')} (incident API: {str(d.get('incident_raw'))[:120]})"
        return f"[{t:6.1f}s] {author:<16} escalation: {d.get('reason') or d.get('error')}"
    return f"[{t:6.1f}s] {author:<16} {json.dumps(d)[:200]}"


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    raw_mode = "--raw" in sys.argv
    if not args:
        sys.exit(__doc__)
    name = args[0]
    message = args[1] if len(args) > 1 else "run"
    location = name.split("/locations/")[1].split("/")[0]
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    url = f"https://{location}-aiplatform.googleapis.com/v1/{name}:streamQuery?alt=sse"
    body = {"class_method": "stream_query", "input": {"user_id": f"cli-{uuid.uuid4().hex[:8]}", "message": message}}
    t0 = time.time()
    with httpx.stream("POST", url, json=body, headers={"Authorization": f"Bearer {creds.token}"}, timeout=900) as r:
        if r.status_code >= 300:
            sys.exit(f"HTTP {r.status_code}: {r.read().decode()[:2000]}")
        for raw in r.iter_lines():
            if not raw.strip():
                continue
            payload = raw[5:].strip() if raw.startswith("data:") else raw
            try:
                ev = json.loads(payload)
            except json.JSONDecodeError:
                print(raw[:200])
                continue
            parts = (ev.get("content") or {}).get("parts") or []
            texts = [p.get("text") for p in parts if isinstance(p, dict) and p.get("text")]
            t = time.time() - t0
            if raw_mode or not texts:
                if ev.get("error_message") or raw_mode:
                    print(json.dumps({"author": ev.get("author"), "text": texts or None, "error": ev.get("error_message")})[:400])
                continue
            for text in texts:
                try:
                    print(describe(ev.get("author", "?"), json.loads(text), t))
                except json.JSONDecodeError:
                    print(f"[{t:6.1f}s] {ev.get('author', '?'):<16} {text[:200]}")
    print(f"done in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
