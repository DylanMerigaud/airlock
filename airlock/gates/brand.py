"""Brand gate: does the asset respect the charter (palette, tone, mandatory mention, exclusions)?

Gemini 2.5 flash reads the asset against the charter text and returns structured findings; the
decision is deterministic on those findings. Structure of the charter: charter.yaml.
"""

from __future__ import annotations

import pathlib
from typing import Any

import yaml

from airlock.gates.base import Asset, GateResult
from airlock.gemini import FAST_MODEL, ask_json, video_part

SOURCE_OF_TRUTH = "brand charter (charter.yaml)"
CHARTER_PATH = pathlib.Path(__file__).resolve().parents[2] / "charter.yaml"

BRAND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "wordmark_seen": {"type": "boolean"},
        "wordmark_timestamps": {"type": "array", "items": {"type": "string"}, "description": "each as mm:ss or mm:ss.s from the start of the clip"},
        "on_screen_text": {"type": "array", "items": {"type": "string"}},
        "dominant_colors_hex": {"type": "array", "items": {"type": "string"}},
        "tone_words": {"type": "array", "items": {"type": "string"}},
        "exclusion_violations": {"type": "array", "items": {"type": "object", "properties": {
            "exclusion": {"type": "string"}, "evidence": {"type": "string"},
            "start": {"type": "string", "description": "mm:ss or mm:ss.s from the start of the clip"}},
            "required": ["exclusion", "evidence"]}},
        "other_brands_seen": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["wordmark_seen", "wordmark_timestamps", "on_screen_text", "dominant_colors_hex", "tone_words", "exclusion_violations", "other_brands_seen"],
}


def clock_to_seconds(value: Any) -> float | None:
    """"mm:ss" or "mm:ss.s" (or "h:mm:ss") to seconds. gemini-2.5-flash asked for a number answers minutes.seconds
    as a decimal (0.26 for 26 s, measured on the Crest excerpt on 2026-09-05), so the schema asks for a clock string
    and this is the only place it is read. A bare number is taken as seconds; anything else is None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    parts = text.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        seconds = 0.0
        for part in parts:
            seconds = seconds * 60 + float(part)
        return round(seconds, 2)
    except ValueError:
        return None


def normalize_timestamps(findings: dict[str, Any]) -> dict[str, Any]:
    """The clock strings the model wrote become the seconds the rest of the gate and the console read
    (`wordmark_timestamps_s`, `start_s`), so a finding's marker lands where the frame is."""
    out = dict(findings)
    out["wordmark_timestamps_s"] = [t for t in (clock_to_seconds(v) for v in findings.get("wordmark_timestamps") or []) if t is not None]
    violations = []
    for v in findings.get("exclusion_violations") or []:
        row = dict(v)
        row["start_s"] = clock_to_seconds(v.get("start"))
        violations.append(row)
    out["exclusion_violations"] = violations
    return out


def load_charter(path: pathlib.Path = CHARTER_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def prompt_for(charter: dict[str, Any]) -> str:
    return (
        "You are checking a video asset against a brand charter. The charter, in YAML:\n\n"
        + yaml.safe_dump(charter, sort_keys=False)
        + f"\nThe wordmark is the exact word \"{charter.get('brand')}\" written on screen or on a product. Report wordmark_seen "
        f"as true only if that exact word appears; a different brand name does not count. Then: every piece of "
        "on-screen text; the dominant colours of the frames as hex; the tone words that describe the delivery; every charter "
        "exclusion that the asset violates, quoting the evidence with its timestamp; any other brand name seen. Be literal. "
        "Write every timestamp as a clock reading from the start of the clip, mm:ss or mm:ss.s (16.5 seconds in is 00:16.5)."
    )


def _hex_close(a: str, b: str, tol: int = 40) -> bool:
    try:
        ra, ga, ba = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
        rb, gb, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    except (ValueError, IndexError):
        return False
    return abs(ra - rb) <= tol and abs(ga - gb) <= tol and abs(ba - bb) <= tol


def decide(findings: dict[str, Any], charter: dict[str, Any]) -> GateResult:
    """Deterministic on the findings; unit-tested without a model."""
    reasons: list[str] = []
    rule_ids: list[str] = []
    brand = charter.get("brand", "")
    if not findings.get("wordmark_seen"):
        reasons.append(f"mandatory mention missing: the {brand} wordmark is never seen")
        rule_ids.append("charter:mandatory_mentions")
    for v in findings.get("exclusion_violations", []):
        where = f", at {v.get('start_s')}s)" if v.get("start_s") is not None else ")"
        reasons.append(f"exclusion violated: {v.get('exclusion')} ({v.get('evidence')}" + where)
        rule_ids.append("charter:exclusions")
    never = {w.lower() for w in (charter.get("tone", {}).get("never") or [])}
    hits = [w for w in findings.get("tone_words", []) if w.lower() in never]
    if hits:
        reasons.append(f"tone outside the charter: {', '.join(hits)}")
        rule_ids.append("charter:tone")
    forbidden = charter.get("palette", {}).get("forbidden") or []
    bad = [c for c in findings.get("dominant_colors_hex", []) if any(_hex_close(c, f) for f in forbidden)]
    if bad:
        reasons.append(f"forbidden palette colour dominant: {', '.join(bad)}")
        rule_ids.append("charter:palette")
    others = [b for b in findings.get("other_brands_seen", []) if b.lower() != brand.lower()]
    if others:
        reasons.append(f"other brand on screen: {', '.join(others)}")
        rule_ids.append("charter:exclusions")
    max_words = charter.get("typography", {}).get("max_words_on_screen")
    if max_words:
        long_lines = [t for t in findings.get("on_screen_text", []) if len(t.split()) > max_words]
        if long_lines:
            reasons.append(f"on-screen text longer than {max_words} words: \"{long_lines[0][:80]}\"")
            rule_ids.append("charter:typography")
    evidence = [findings]
    if reasons:
        return GateResult(gate="brand", status="BLOCK", reasons=reasons, evidence=evidence, rule_ids=sorted(set(rule_ids)), source_of_truth=SOURCE_OF_TRUTH)
    return GateResult(gate="brand", status="PASS", reasons=[f"{brand} wordmark seen, palette, tone and exclusions respected"], evidence=evidence,
                      rule_ids=["charter:mandatory_mentions", "charter:palette", "charter:tone", "charter:exclusions"], source_of_truth=SOURCE_OF_TRUTH)


def check(asset: Asset) -> GateResult:
    charter = load_charter()
    findings, usage = ask_json(FAST_MODEL, [video_part(asset.path, asset.gcs_uri, asset.mime_type), prompt_for(charter)], BRAND_SCHEMA)
    result = decide(normalize_timestamps(findings), charter)
    result.evidence.append({"model": usage})
    return result
