"""Rights gate: which identifiable brands, faces and explicit content does the asset carry, and
does the registry clear them?

Source of truth: the Video Intelligence API (LOGO_RECOGNITION, FACE_DETECTION, TEXT_DETECTION,
EXPLICIT_CONTENT_DETECTION) confronted with rights-registry.yaml. The registry is the contract: an
identifiable element the registry does not clear blocks, whether the registry names it as
not_cleared or does not know it at all.

Registry names are matched token-wise against the on-screen text: every word of the name has to
appear, in one text line or across the lines Video Intelligence read within a few seconds of each
other (a seal splits "AMERICAN DENTAL" and "ASSOCIATION" into two lines). A release clears the
faces of the asset it names (`asset_id`) or, when it says `covers: all`, every asset; a release
list that names another asset clears nothing here. Video Intelligence gives no age, so a minor's
face gets the same rule as an adult's (a known gap, README), and it reads no audio, so music is
not checked at all.
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
    three jobs ran at once; 8 s clip 30 to 90 s. Measured 2026-09-02 (docs/RUNS.md): four parallel
    one-feature operations finish in the same wall time as one four-feature operation (30 s excerpt
    median 49.0 s against 49.6 s), logo recognition being the long pole; the spread is the service's. A timeout (AIRLOCK_VI_TIMEOUT_S) raises, and the
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


TOKEN = re.compile(r"[a-z0-9]+")
TOKEN_WINDOW_S = 3.0  # lines whose spans start within this many seconds of each other are read together


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


def _line_start(t: dict[str, Any]) -> float:
    spans = t.get("spans") or []
    return float(spans[0].get("start", 0.0)) if spans else 0.0


def brands_in_text(texts: list[dict[str, Any]], registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Registry brand names that appear in detected on-screen text, token-wise.

    A name matches when every one of its words is a whole word of one text line, or of the lines
    read within TOKEN_WINDOW_S of that line (the ADA seal comes back as two lines). Single-word
    names ("Crest") therefore match as whole words only, never inside another word.
    """
    found: dict[str, dict[str, Any]] = {}
    lines = sorted(((t, set(tokens(t.get("text", "")))) for t in texts), key=lambda x: _line_start(x[0]))
    for b in registry.get("brands", []):
        need = set(tokens(b["name"]))
        if not need:
            continue
        for t, own in lines:
            across = not need <= own
            if across:
                if not need & own:  # the line has to carry at least one word of the name
                    continue
                start = _line_start(t)
                pooled = set(own)
                for u, other in lines:
                    if u is not t and abs(_line_start(u) - start) <= TOKEN_WINDOW_S:
                        pooled |= other
                if not need <= pooled:
                    continue
            found[b["name"]] = {"name": b["name"], "how": "on_screen_text", "spans": (t.get("spans") or [])[:3], "across_lines": across}
            break
    return list(found.values())


def releases_for(asset_refs: set[str] | None, registry: dict[str, Any]) -> list[dict[str, Any]]:
    """The releases on file that apply to THIS asset: those naming one of its references (its id or its
    file stem) and those that say covers: all. A release for another asset clears nothing here."""
    refs = {r for r in (asset_refs or set()) if r}
    out = []
    for rel in registry.get("faces", {}).get("releases") or []:
        if not isinstance(rel, dict):
            continue
        if str(rel.get("covers", "")).lower() == "all" or rel.get("asset_id") in refs:
            out.append(rel)
    return out


def asset_refs(asset: Asset) -> set[str]:
    refs = {asset.asset_id}
    for loc in (asset.path, asset.gcs_uri):
        if loc:
            refs.add(pathlib.Path(loc).stem)
    return refs


def decide(annotations: dict[str, Any], registry: dict[str, Any], refs: set[str] | None = None) -> GateResult:
    """Deterministic on the annotations; unit-tested without the API. refs names the asset (its id, its
    file stem) so a release can be matched to it."""
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
        findings.append({"element": "brand", "name": hit["name"], "status": status, "how": "on_screen_text", "first_seen_s": first.get("start"),
                         "across_lines": hit.get("across_lines", False)})
        if status != "cleared":
            where = "on-screen text" + (" across lines" if hit.get("across_lines") else "")
            reasons.append(f"brand {hit['name']} ({status}, {where} at {first.get('start')}s)" + (f": {entry.get('note')}" if entry and entry.get("note") else ""))
            rule_ids.append("registry:brands:" + ("not_cleared" if status == "not_cleared" else "unknown"))
    faces = annotations.get("faces", [])
    releases = releases_for(refs, registry)
    if faces and policy.get("unknown_face", "BLOCK") == "BLOCK":
        first = min(faces, key=lambda f: f["start"])
        if releases:
            findings.append({"element": "faces", "tracks": len(faces), "first_seen_s": first["start"], "released_by": [r.get("asset_id") or "all" for r in releases],
                             "status": "released"})
        else:
            reasons.append(f"{len(faces)} face track(s) with no release on file for this asset (first at {first['start']}s)")
            rule_ids.append("registry:faces:no_release")
            findings.append({"element": "faces", "tracks": len(faces), "first_seen_s": first["start"], "releases_on_file": 0})
    threshold = policy.get("explicit_content_likelihood_block_at", "LIKELY")
    bad = {k: v for k, v in annotations.get("explicit_frames", {}).items() if LIKELIHOOD_ORDER.index(k) >= LIKELIHOOD_ORDER.index(threshold)}
    if bad:
        reasons.append(f"explicit content likelihood at or above {threshold} on {sum(bad.values())} frame(s)")
        rule_ids.append("registry:explicit_content")
        findings.append({"element": "explicit", "frames": bad})
    texts = annotations.get("texts", [])
    evidence = [{"findings": findings, "logos": annotations.get("logos", []), "face_tracks": len(faces), "releases_applied": len(releases),
                 "text_lines": len(texts), "texts": [{"text": t.get("text"), "start": _line_start(t)} for t in texts][:80],
                 "explicit_frames": annotations.get("explicit_frames", {}),
                 "features": annotations.get("features", []), "duration_s": annotations.get("duration_s", 0.0)}]
    if reasons:
        return GateResult(gate="rights", status="BLOCK", reasons=reasons, evidence=evidence, rule_ids=sorted(set(rule_ids)), source_of_truth=SOURCE_OF_TRUTH)
    cleared = [f["name"] for f in findings if f.get("status") == "cleared"]
    return GateResult(gate="rights", status="PASS", evidence=evidence, rule_ids=["registry:brands", "registry:faces", "registry:explicit_content"],
                      reasons=[("cleared brand(s): " + ", ".join(cleared) + "; " if cleared else "no brand, ")
                               + ("faces released" if faces else "no unreleased face") + ", no explicit content"],
                      source_of_truth=SOURCE_OF_TRUTH)


def check(asset: Asset) -> GateResult:
    return decide(annotate(asset), load_registry(), asset_refs(asset))
