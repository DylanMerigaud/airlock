"""Run the deployed Agent Engine agent over REST and print every event.

Usage: python scripts/query_agent_engine.py <reasoning_engine_resource_name> [message]
The console (M4) uses the same :streamQuery endpoint.
"""

from __future__ import annotations

import json
import sys
import uuid

import google.auth
import google.auth.transport.requests
import httpx


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    name = sys.argv[1]
    message = sys.argv[2] if len(sys.argv) > 2 else "run the spike"
    location = name.split("/locations/")[1].split("/")[0]
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    url = f"https://{location}-aiplatform.googleapis.com/v1/{name}:streamQuery?alt=sse"
    body = {"class_method": "stream_query", "input": {"user_id": f"spike-{uuid.uuid4().hex[:8]}", "message": message}}
    with httpx.stream("POST", url, json=body, headers={"Authorization": f"Bearer {creds.token}"}, timeout=300) as r:
        if r.status_code >= 300:
            sys.exit(f"HTTP {r.status_code}: {r.read().decode()[:2000]}")
        for raw in r.iter_lines():
            if not raw.strip():
                continue
            payload = raw[5:].strip() if raw.startswith("data:") else raw
            try:
                ev = json.loads(payload)
            except json.JSONDecodeError:
                print(raw)
                continue
            parts = (ev.get("content") or {}).get("parts") or []
            texts = [p.get("text") for p in parts if isinstance(p, dict) and p.get("text")]
            print(json.dumps({"author": ev.get("author"), "id": ev.get("id"), "text": texts or None, "error": ev.get("error_message")}))


if __name__ == "__main__":
    main()
