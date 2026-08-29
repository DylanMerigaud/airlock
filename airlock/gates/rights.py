"""Rights gate: which identifiable brands, faces and explicit content does the asset carry, and
does the registry clear them?

Source of truth: the Video Intelligence API (LOGO_RECOGNITION, FACE_DETECTION, TEXT_DETECTION,
EXPLICIT_CONTENT_DETECTION) confronted with rights-registry.yaml. The registry is the contract: an
identifiable element the registry does not clear blocks, whether the registry names it as
not_cleared or does not know it at all.
"""

from __future__ import annotations

import os
import pathlib
import re
from typing import Any

import yaml

from airlock.gates.base import Asset, GateResult

SOURCE_OF_TRUTH = "Video Intelligence API (logos, faces, text, explicit content) against rights-registry.yaml"
REGISTRY_PATH = pathlib.Path(__file__).resolve().parents[2] / "rights-registry.yaml"
LIKELIHOOD_ORDER = ["VERY_UNLIKELY", "UNLIKELY", "POSSIBLE", "LIKELY", "VERY_LIKELY"]


def load_registry(path: pathlib.Path = REGISTRY_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def _secs(d: Any) -> float:
    return round(getattr(d, "seconds", 0) + getattr(d, "microseconds", 0) / 1e6, 2)


FEATURE_NAMES = {"logo": "LOGO_RECOGNITION", "face": "FACE_DETECTION", "text": "TEXT_DETECTION", "explicit": "EXPLICIT_CONTENT_DETECTION"}


def configured_features() -> list[str]:
    """AIRLOCK_VI_FEATURES, e.g. "logo,face,text"; default all four. Latency scales with the set."""
    raw = os.environ.get("AIRLOCK_VI_FEATURES", "logo,face,text,explicit")
    names = [x.strip() for x in raw.split(",") if x.strip()]
    unknown = [n for n in names if n not in FEATURE_NAMES]
    if unknown:
        raise ValueError(f"unknown AIRLOCK_VI_FEATURES entries: {unknown}")
    return names


def annotate(asset: Asset) -> dict[str, Any]:
    """Call Video Intelligence and flatten what the gate needs.

    Measured 2026-08-28: 60 s clip with four features 246 s; 30 s excerpt 59 s alone and 598 s when
    three jobs ran at once; 8 s clip 30 to 90 s. A timeout (AIRLOCK_VI_TIMEOUT_S) raises, and the
    envelope turns it into an ERROR the verdict treats as an instrument failure.
    """
    from google.cloud import videointelligence_v1 as vi

    client = vi.VideoIntelligenceServiceClient()
    names = configured_features()
    features = [getattr(vi.Feature, FEATURE_NAMES[n]) for n in names]
    request: dict[str, Any] = {"features": features, "video_context": {"face_detection_config": {"include_bounding_boxes": False, "include_attributes": False}}}
    if asset.gcs_uri:
        request["input_uri"] = asset.gcs_uri
    else:
        request["input_content"] = pathlib.Path(asset.path).read_bytes()
    op = client.annotate_video(request=request)
    a = op.result(timeout=float(os.environ.get("AIRLOCK_VI_TIMEOUT_S", "600"))).annotation_results[0]
    logos = [{"name": l.entity.description, "entity_id": l.entity.entity_id,
              "spans": [{"start": _secs(t.segment.start_time_offset), "end": _secs(t.segment.end_time_offset), "confidence": round(t.confidence, 3)} for t in l.tracks]}
             for l in a.logo_recognition_annotations]
    texts = [{"text": t.text, "spans": [{"start": _secs(s.segment.start_time_offset), "end": _secs(s.segment.end_time_offset)} for s in t.segments]} for t in a.text_annotations]
    faces = [{"start": _secs(t.segment.start_time_offset), "end": _secs(t.segment.end_time_offset)} for f in a.face_detection_annotations for t in f.tracks]
    explicit: dict[str, int] = {}
    for f in a.explicit_annotation.frames:
        k = vi.Likelihood(f.pornography_likelihood).name
        explicit[k] = explicit.get(k, 0) + 1
    duration_s = _secs(a.segment.end_time_offset) if getattr(a, "segment", None) else 0.0
    return {"logos": logos, "texts": texts, "faces": faces, "explicit_frames": explicit, "features": names, "duration_s": duration_s}


def _brand_status(name: str, registry: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    for b in registry.get("brands", []):
        if b["name"].lower() == name.lower():
            return b.get("status", "unknown"), b
    return "unknown", None


def brands_in_text(texts: list[dict[str, Any]], registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Registry brand names that appear in detected on-screen text (case-insensitive, whole word)."""
    found: dict[str, dict[str, Any]] = {}
    for b in registry.get("brands", []):
        pat = re.compile(r"\b" + re.escape(b["name"]) + r"\b", re.I)
        for t in texts:
            if pat.search(t["text"]):
                row = found.setdefault(b["name"], {"name": b["name"], "how": "on_screen_text", "spans": []})
                row["spans"].extend(t["spans"][:3])
    return list(found.values())


def decide(annotations: dict[str, Any], registry: dict[str, Any]) -> GateResult:
    """Deterministic on the annotations; unit-tested without the API."""
    policy = registry.get("policy", {})
    reasons: list[str] = []
    rule_ids: list[str] = []
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for logo in annotations.get("logos", []):
        status, entry = _brand_status(logo["name"], registry)
        first = logo["spans"][0] if logo["spans"] else {}
        findings.append({"element": "brand", "name": logo["name"], "status": status, "how": "logo", "first_seen_s": first.get("start"), "confidence": first.get("confidence")})
        seen.add(logo["name"].lower())
        if status == "unknown":
            # The API's logo names were wrong on 6 of 10 real 1950s spots (eval of 2026-08-29): the name is a guess.
            reasons.append(f"a logo the registry does not know at {first.get('start')}s (Video Intelligence's guess: {logo['name']}, confidence {first.get('confidence')})")
            rule_ids.append("registry:brands:unknown")
        elif status != "cleared":
            reasons.append(f"brand {logo['name']} ({status}, logo at {first.get('start')}s, confidence {first.get('confidence')})"
                           + (f": {entry.get('note')}" if entry and entry.get("note") else ""))
            rule_ids.append("registry:brands:not_cleared")
    for hit in brands_in_text(annotations.get("texts", []), registry):
        if hit["name"].lower() in seen:
            continue
        status, entry = _brand_status(hit["name"], registry)
        first = hit["spans"][0] if hit["spans"] else {}
        findings.append({"element": "brand", "name": hit["name"], "status": status, "how": "on_screen_text", "first_seen_s": first.get("start")})
        if status != "cleared":
            reasons.append(f"brand {hit['name']} ({status}, on-screen text at {first.get('start')}s)" + (f": {entry.get('note')}" if entry and entry.get("note") else ""))
            rule_ids.append("registry:brands:" + ("not_cleared" if status == "not_cleared" else "unknown"))
    faces = annotations.get("faces", [])
    releases = registry.get("faces", {}).get("releases") or []
    if faces and not releases and policy.get("unknown_face", "BLOCK") == "BLOCK":
        first = min(faces, key=lambda f: f["start"])
        reasons.append(f"{len(faces)} face track(s) with no release on file (first at {first['start']}s)")
        rule_ids.append("registry:faces:no_release")
        findings.append({"element": "faces", "tracks": len(faces), "first_seen_s": first["start"], "releases_on_file": len(releases)})
    threshold = policy.get("explicit_content_likelihood_block_at", "LIKELY")
    bad = {k: v for k, v in annotations.get("explicit_frames", {}).items() if LIKELIHOOD_ORDER.index(k) >= LIKELIHOOD_ORDER.index(threshold)}
    if bad:
        reasons.append(f"explicit content likelihood at or above {threshold} on {sum(bad.values())} frame(s)")
        rule_ids.append("registry:explicit_content")
        findings.append({"element": "explicit", "frames": bad})
    evidence = [{"findings": findings, "logos": annotations.get("logos", []), "face_tracks": len(faces),
                 "text_lines": len(annotations.get("texts", [])), "explicit_frames": annotations.get("explicit_frames", {}),
                 "features": annotations.get("features", []), "duration_s": annotations.get("duration_s", 0.0)}]
    if reasons:
        return GateResult(gate="rights", status="BLOCK", reasons=reasons, evidence=evidence, rule_ids=sorted(set(rule_ids)), source_of_truth=SOURCE_OF_TRUTH)
    cleared = [f["name"] for f in findings if f.get("status") == "cleared"]
    return GateResult(gate="rights", status="PASS", evidence=evidence, rule_ids=["registry:brands", "registry:faces", "registry:explicit_content"],
                      reasons=[("cleared brand(s): " + ", ".join(cleared) + "; " if cleared else "no brand, ") + "no unreleased face, no explicit content"],
                      source_of_truth=SOURCE_OF_TRUTH)


def check(asset: Asset) -> GateResult:
    return decide(annotate(asset), load_registry())
