"""Gemini on Vertex AI: one client, video in, JSON out.

Models are fixed by the plan: gemini-2.5-pro reads regulatory text and extracts claims with
timestamps (its timestamps are in seconds; flash mis-scaled them on the 60 s probe of 2026-08-28),
gemini-2.5-flash does the cheaper reads (brand charter, escalation text).
"""

from __future__ import annotations

import functools
import json
import os
import pathlib
from typing import Any

from google import genai
from google.genai import types

CLAIM_MODEL = "gemini-2.5-pro"
FAST_MODEL = "gemini-2.5-flash"
INLINE_LIMIT_BYTES = 19_000_000


@functools.lru_cache(maxsize=1)
def client() -> genai.Client:
    """One client per process: a temporary Client gets collected while its request is in flight."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "airlock-agentic-cinema")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    return genai.Client(vertexai=True, project=project, location=location)


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
    return json.loads(resp.text), usage
