"""The deployed pipeline over REST: one streaming client shared by the CLI
(scripts/query_agent_engine.py) and the daily proof (airlock.daily_proof).

The endpoint is `:streamQuery?alt=sse` on the regional Vertex AI host. The body names the ADK
app's `stream_query` method; every SSE line is one ADK event, and the text parts of an event are
the JSON payloads the pipeline's agents emit (stage running, done, grafana, verdict, escalation).
No Vertex SDK: the console (M4) and this module use the same HTTP call.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from airlock import settings


def resource_from_env() -> str:
    """The reasoning engine to query: AGENT_ENGINE_RESOURCE, or the deployed pipeline (airlock.settings)."""
    return settings.engine_resource()


@dataclass
class Event:
    """One SSE line from the pipeline: its author, the text parts, and the seconds since the request."""

    author: str
    t: float
    texts: list[str] = field(default_factory=list)
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    unparsed: str | None = None  # a line that was not JSON at all (a keepalive, a proxy message)

    def payloads(self) -> list[dict[str, Any]]:
        """The text parts that are JSON objects, parsed; the pipeline's agents emit only those."""
        out = []
        for text in self.texts:
            try:
                d = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(d, dict):
                out.append(d)
        return out


def parse_sse_line(raw: str, t: float) -> Event | None:
    """One SSE line to an Event; None for a blank line."""
    if not raw.strip():
        return None
    payload = raw[5:].strip() if raw.startswith("data:") else raw
    try:
        ev = json.loads(payload)
    except json.JSONDecodeError:
        return Event(author="", t=t, unparsed=raw)
    if not isinstance(ev, dict):
        return Event(author="", t=t, unparsed=raw)
    parts = (ev.get("content") or {}).get("parts") or []
    texts = [str(p["text"]) for p in parts if isinstance(p, dict) and p.get("text")]
    return Event(author=ev.get("author") or "?", t=t, texts=texts, error=ev.get("error_message"), raw=ev)


def stream_query(name: str, message: str, timeout_s: float = 900, user_id: str | None = None) -> Iterator[Event]:
    """POST :streamQuery on the reasoning engine `name` and yield its events as they arrive.

    `message` is what the pipeline reads: a GCS URI, or a JSON object such as
    {"gcs_uri": "...", "asset_id": "...", "mute": ["rights"]}. Raises RuntimeError on a non-2xx answer.
    """
    import google.auth
    import google.auth.transport.requests

    location = name.split("/locations/")[1].split("/")[0]
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    url = f"https://{location}-aiplatform.googleapis.com/v1/{name}:streamQuery?alt=sse"
    body = {"class_method": "stream_query", "input": {"user_id": user_id or f"cli-{uuid.uuid4().hex[:8]}", "message": message}}
    t0 = time.time()
    with httpx.stream("POST", url, json=body, headers={"Authorization": f"Bearer {creds.token}"}, timeout=timeout_s) as r:
        if r.status_code >= 300:
            raise RuntimeError(f"HTTP {r.status_code}: {r.read().decode()[:2000]}")
        for raw in r.iter_lines():
            ev = parse_sse_line(raw, time.time() - t0)
            if ev is not None:
                yield ev


def describe(author: str, d: dict[str, Any], t: float) -> str:
    """One readable line per pipeline payload, the shape scripts/query_agent_engine.py prints."""
    st = d.get("stage")
    if st == "running":
        return f"[{t:6.1f}s] {author:<16} running  {d.get('gate')}" + ("  (telemetry muted)" if d.get("telemetry_muted") else "")
    if st == "done":
        return f"[{t:6.1f}s] {author:<16} {d.get('status'):<6} {d.get('elapsed_ms', 0):>6} ms  {(d.get('reasons') or [''])[0][:140]}"
    if st == "grafana":
        vals = {k: v.get("value") for k, v in (d.get("answers") or {}).items()}
        return f"[{t:6.1f}s] {author:<16} grafana  {d.get('gate'):<11} {d.get('health')}; {d.get('calibration')}  {vals}"
    if st == "verdict":
        head = (f"[{t:6.1f}s] {author:<16} VERDICT {d.get('status')} ({d.get('motive')}) needs_human={d.get('needs_human')} "
                f"annotation={d.get('annotation_id')} trace={d.get('trace_id')} {d.get('elapsed_ms')} ms")
        return head + "".join(f"\n{'':>26}{r[:200]}" for r in d.get("reasons", []))
    if st == "investigation":
        if d.get("tool"):
            return f"[{t:6.1f}s] {author:<16} investigation  step {d.get('step')}: {d.get('tool')} {str(d.get('args') or '')[:120]}"
        if d.get("conclusion") or d.get("note"):
            return f"[{t:6.1f}s] {author:<16} INVESTIGATION {d.get('kind') or ''} {str(d.get('conclusion') or d.get('note'))[:220]}"
        return f"[{t:6.1f}s] {author:<16} investigation  {json.dumps(d)[:160]}"
    if st == "escalation":
        if d.get("opened"):
            return f"[{t:6.1f}s] {author:<16} INCIDENT {d.get('incident_id')} {d.get('incident_url')}"
        if d.get("attached"):
            return f"[{t:6.1f}s] {author:<16} JOINED INCIDENT {d.get('incident_id')} {d.get('incident_url')}"
        if d.get("fallback"):
            return (f"[{t:6.1f}s] {author:<16} FALLBACK needs-human annotation {d.get('fallback_annotation_id')} "
                    f"(incident API: {str(d.get('incident_raw'))[:120]})")
        return f"[{t:6.1f}s] {author:<16} escalation: {d.get('reason') or d.get('error')}"
    return f"[{t:6.1f}s] {author:<16} {json.dumps(d)[:200]}"
