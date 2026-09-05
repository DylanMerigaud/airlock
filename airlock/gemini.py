"""Gemini on Vertex AI: one client, video in, JSON out.

Models are fixed by the plan: gemini-2.5-pro reads regulatory text and extracts claims with
timestamps (its timestamps are in seconds; flash mis-scaled them on the 60 s probe of 2026-08-28),
gemini-2.5-flash does the cheaper reads (brand charter, escalation text).
"""

from __future__ import annotations

import json
import pathlib
import threading
from typing import Any

from google import genai
from google.genai import types

from airlock import settings

CLAIM_MODEL = "gemini-2.5-pro"
FAST_MODEL = "gemini-2.5-flash"
INLINE_LIMIT_BYTES = 19_000_000


_client_lock = threading.Lock()
_client: genai.Client | None = None


def client() -> genai.Client:
    """One client per process, built under a lock.

    A temporary Client gets collected while its request is in flight (measured 2026-08-28, "Cannot
    send a request, as the client has been closed"); two gates constructing it at once from two
    threads reproduced the same error through the losing instance's destructor.
    """
    global _client
    with _client_lock:
        if _client is None:
            _client = genai.Client(vertexai=True, project=settings.project(), location=settings.region())
        return _client


def video_part(path: str, gcs_uri: str | None, mime_type: str = "video/mp4") -> types.Part:
    """Prefer the GCS URI; fall back to inline bytes for short local files."""
    if gcs_uri:
        return types.Part.from_uri(file_uri=gcs_uri, mime_type=mime_type)
    data = pathlib.Path(path).read_bytes()
    if len(data) > INLINE_LIMIT_BYTES:
        raise ValueError(f"{path} is {len(data)} bytes; upload it to GCS first (inline limit {INLINE_LIMIT_BYTES})")
    return types.Part.from_bytes(data=data, mime_type=mime_type)


def ask_json(model: str, parts: list[Any], schema: dict[str, Any], temperature: float = 0.0) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call the model with a JSON schema; return (parsed answer, usage)."""
    resp = client().models.generate_content(
        model=model,
        contents=parts,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema, temperature=temperature),
    )
    usage = {"model": model,
             "prompt_tokens": getattr(resp.usage_metadata, "prompt_token_count", None),
             "output_tokens": getattr(resp.usage_metadata, "candidates_token_count", None)}
    text = resp.text
    if text is None:
        raise RuntimeError(f"{model} returned no text: {refusal(resp)}")
    return json.loads(text), usage


def refusal(resp: Any) -> str:
    """Why an answer carries no text: the finish reason (SAFETY, RECITATION, MAX_TOKENS...) of the
    first candidate and the prompt block reason when the prompt itself was refused. Named so the
    gate's ERROR says "blocked for safety" rather than "the JSON object must be str"."""
    parts: list[str] = []
    feedback = getattr(resp, "prompt_feedback", None)
    if feedback is not None and getattr(feedback, "block_reason", None):
        message = getattr(feedback, "block_reason_message", None)
        parts.append(f"prompt blocked: {feedback.block_reason}" + (f" ({message})" if message else ""))
    candidates = getattr(resp, "candidates", None) or []
    for c in candidates[:1]:
        reason = getattr(c, "finish_reason", None)
        if reason is not None:
            parts.append(f"finish reason {getattr(reason, 'name', reason)}" + (f": {c.finish_message}" if getattr(c, "finish_message", None) else ""))
        ratings = [f"{getattr(r.category, 'name', r.category)}={getattr(r.probability, 'name', r.probability)}"
                   for r in (getattr(c, "safety_ratings", None) or []) if getattr(r, "blocked", False)]
        if ratings:
            parts.append("safety: " + ", ".join(ratings))
    if not candidates and not parts:
        parts.append("no candidate in the answer")
    return "; ".join(parts) or "unknown reason"
