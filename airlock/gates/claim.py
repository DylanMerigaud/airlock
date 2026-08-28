"""Claim gate: what does the asset assert, and is any of it a claim the rules require proof for?

Two layers. Gemini 2.5 pro extracts every spoken or on-screen claim with timestamps, a verbatim
quote, a kind and an endorser (the extraction schema is the one probed on 2026-08-28). Then a
deterministic rule maps each kind to the FTC section and the ASA precedent it falls under, and
blocks when a regulated claim has no substantiation on file. The model never decides; it reads.
"""

from __future__ import annotations

import pathlib
from typing import Any

import yaml

from airlock.gates.base import Asset, GateResult
from airlock.gemini import CLAIM_MODEL, ask_json, video_part

SOURCE_OF_TRUTH = "16 CFR Part 255 (rules/ftc-16-cfr-255.md), ASA rulings A26-1337640 and G26-1344778"

CLAIM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {"type": "array", "items": {"type": "object", "properties": {
            "start_s": {"type": "number"}, "end_s": {"type": "number"},
            "channel": {"type": "string", "enum": ["spoken", "on_screen_text"]},
            "quote": {"type": "string"},
            "kind": {"type": "string", "enum": ["efficacy", "health", "comparative", "superlative", "expert_endorsement",
                                                "organization_endorsement", "consumer_testimonial", "price", "other"]},
            "endorser": {"type": "string"}},
            "required": ["start_s", "end_s", "channel", "quote", "kind"]}},
        "summary": {"type": "string"},
    },
    "required": ["claims", "summary"],
}

PROMPT = (
    "You are a brand-safety reviewer. Watch this asset. Return every claim made to the viewer, spoken or written on "
    "screen, with its timestamps in seconds, a verbatim quote, and a kind. Name the endorser when there is one (a person, "
    "a profession such as 'dentists', or an organization). A slogan with no factual content is kind 'other'. "
    "Be exhaustive and literal; do not invent."
)

# Which rule a claim kind falls under, and the precedent whose claim shape matches.
RULES: dict[str, dict[str, Any]] = {
    "efficacy":                 {"ftc": ["16 CFR 255.1(a)", "16 CFR 255.2(b)"], "asa": ["ASA A26-1337640 (CAP 3.1, 3.7)"],
                                 "why": "an efficacy claim needs competent and reliable evidence on file"},
    "health":                   {"ftc": ["16 CFR 255.1(a)"], "asa": ["ASA A26-1337640 (CAP 3.7, 12.11)"],
                                 "why": "a health claim needs substantiation, and a medicinal one a licence"},
    "consumer_testimonial":     {"ftc": ["16 CFR 255.2(a)", "16 CFR 255.2(b)"], "asa": ["ASA A26-1337640 (CAP 3.7)"],
                                 "why": "a testimonial must reflect what consumers can generally expect, or disclose it does not"},
    "expert_endorsement":       {"ftc": ["16 CFR 255.3"], "asa": ["ASA A26-1337640 (CAP 3.7)"],
                                 "why": "an expert endorsement must be supported by an actual exercise of that expertise"},
    "organization_endorsement": {"ftc": ["16 CFR 255.4"], "asa": [],
                                 "why": "an organization endorsement must reflect the collective judgment of the organization"},
    "comparative":              {"ftc": ["16 CFR 255.1(a)"], "asa": ["ASA G26-1344778 (CAP 3.1, 3.3, 3.32)"],
                                 "why": "a comparison needs its basis on the same screen"},
    "superlative":              {"ftc": ["16 CFR 255.1(a)"], "asa": ["ASA G26-1344778 (CAP 3.1, 3.3)"],
                                 "why": "a superlative is a comparison with every competitor and needs its basis"},
}
ADVISORY_KINDS = {"price", "other"}


def load_substantiation(asset: Asset) -> dict[str, Any]:
    """Evidence on file for this asset: <asset path>.substantiation.yaml, absent for both demo assets."""
    p = pathlib.Path(asset.path).with_suffix(".substantiation.yaml")
    if p.exists():
        return yaml.safe_load(p.read_text()) or {}
    return {}


def extract_claims(asset: Asset) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    answer, usage = ask_json(CLAIM_MODEL, [video_part(asset.path, asset.gcs_uri, asset.mime_type), PROMPT], CLAIM_SCHEMA)
    return answer.get("claims", []), {"summary": answer.get("summary", "")}, usage


def decide(claims: list[dict[str, Any]], substantiation: dict[str, Any]) -> GateResult:
    """The deterministic rule, unit-tested without a model."""
    proven = {str(k).strip().lower() for k in (substantiation.get("claims") or {}).keys()}
    blocking: list[dict[str, Any]] = []
    advisory: list[dict[str, Any]] = []
    rule_ids: list[str] = []
    for c in claims:
        kind = c.get("kind", "other")
        row = {"start_s": c.get("start_s"), "end_s": c.get("end_s"), "channel": c.get("channel"), "quote": c.get("quote"),
               "kind": kind, "endorser": c.get("endorser")}
        if kind in ADVISORY_KINDS:
            advisory.append(row)
            continue
        rule = RULES[kind]
        row["rules"] = rule["ftc"] + rule["asa"]
        row["why"] = rule["why"]
        if str(c.get("quote", "")).strip().lower() in proven:
            row["substantiated_by"] = substantiation["claims"][c["quote"]]
            advisory.append(row)
            continue
        blocking.append(row)
        for r in row["rules"]:
            if r not in rule_ids:
                rule_ids.append(r)
    evidence = [{"blocking_claims": blocking, "advisory_claims": advisory, "claims_total": len(claims)}]
    if blocking:
        first = blocking[0]
        reasons = [f"{len(blocking)} regulated claim(s) with no substantiation on file; first at {first['start_s']}s: "
                   f"\"{first['quote']}\" ({first['kind']}, {first['rules'][0]})"]
        return GateResult(gate="claim", status="BLOCK", reasons=reasons, evidence=evidence, rule_ids=rule_ids, source_of_truth=SOURCE_OF_TRUTH)
    reasons = [f"no regulated claim without substantiation ({len(claims)} claim(s) read, {len(advisory)} advisory)"]
    return GateResult(gate="claim", status="PASS", reasons=reasons, evidence=evidence, rule_ids=["16 CFR 255.1"], source_of_truth=SOURCE_OF_TRUTH)


def check(asset: Asset) -> GateResult:
    claims, extra, usage = extract_claims(asset)
    result = decide(claims, load_substantiation(asset))
    result.evidence.append({"model": usage, **extra})
    return result
