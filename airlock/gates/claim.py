"""Claim gate: what does the asset assert, and is any of it a claim the rules require proof for?

Two layers. Gemini 2.5 pro extracts every spoken or on-screen claim with timestamps, a verbatim
quote, a kind and an endorser (the extraction schema is the one probed on 2026-08-28). Then a
deterministic rule maps each kind to the rule it falls under and blocks when a regulated claim has
no substantiation on file. The model labels; the rule decides on the labels.

Which rule, by kind (rules/ftc-16-cfr-255.md, rules/ftc-substantiation.md, rules/asa-rulings.md):
  endorsements (consumer testimonial, expert, organisation, undisclosed connection): 16 CFR Part 255,
    the Endorsement Guides, which are about what an endorser says and who the endorser is;
  the advertiser's own efficacy, health, comparative and superlative claims: FTC Act section 5 and
    the FTC Policy Statement Regarding Advertising Substantiation (a reasonable basis before the
    claim runs), CAP Code 3.7 in the UK; a comparison also 16 CFR 14.15 and CAP 3.32;
  puffery (subjective praise no reasonable viewer reads as a fact) and price: advisory, not blocked.
The US and UK rules are both cited on every regulated claim: the gate does not know the market
the asset airs in (a known gap, README).

Substantiation is a YAML file beside the asset (<asset>.substantiation.yaml, locally or in GCS)
whose `claims` map a quote to the study on file. Quotes are matched normalised (case, whitespace,
trailing punctuation), never raw.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

import yaml

from airlock.gates.base import Asset, GateResult
from airlock.gemini import CLAIM_MODEL, ask_json, video_part

SOURCE_OF_TRUTH = ("16 CFR Part 255 (rules/ftc-16-cfr-255.md), FTC Act section 5 and the substantiation policy statement "
                   "(rules/ftc-substantiation.md), ASA rulings A26-1337640 and G26-1344778 (rules/asa-rulings.md)")

CLAIM_KINDS = ["efficacy", "health", "comparative", "superlative", "expert_endorsement", "organization_endorsement",
               "consumer_testimonial", "material_connection", "puffery", "price", "other"]

CLAIM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {"type": "array", "items": {"type": "object", "properties": {
            "start_s": {"type": "number"}, "end_s": {"type": "number"},
            "channel": {"type": "string", "enum": ["spoken", "on_screen_text"]},
            "quote": {"type": "string"},
            "kind": {"type": "string", "enum": CLAIM_KINDS},
            "endorser": {"type": "string"}},
            "required": ["start_s", "end_s", "channel", "quote", "kind"]}},
        "summary": {"type": "string"},
    },
    "required": ["claims", "summary"],
}

PROMPT = (
    "You are a brand-safety reviewer. Watch this asset. Return every claim made to the viewer, spoken or written on "
    "screen, with its timestamps in seconds, a verbatim quote, and a kind. Name the endorser when there is one (a person, "
    "a profession such as 'dentists', or an organization). Kinds: "
    "efficacy (the product does or achieves something measurable), "
    "health (a health, medical, safety or nutritional effect), "
    "comparative (against a named or implied competitor, 'better than', 'fewer than'), "
    "superlative (a ranking stated as a fact: '#1', 'most trusted', 'best-selling'), "
    "expert_endorsement (a professional or expert vouches for it), "
    "organization_endorsement (an organization, seal or council vouches for it), "
    "consumer_testimonial (a consumer reports their own result or experience), "
    "material_connection (an endorser presented as independent whose paid, employment, family or business connection "
    "to the advertiser is stated or evident but not disclosed to the viewer at the moment of the endorsement), "
    "puffery (subjective praise no reasonable viewer takes as a measurable fact: 'the most exciting sound in town', "
    "'a great new taste'), "
    "price (a price, discount or offer), "
    "other (a slogan or statement with no factual content and no praise). "
    "Be exhaustive and literal; do not invent."
)

# Citations, as rule ids. The strings are stable identifiers the verdict, the console and the eval read.
FTC_ACT_5 = "FTC Act section 5 (15 U.S.C. 45)"
FTC_SUBSTANTIATION = "FTC Policy Statement Regarding Advertising Substantiation (1983)"
FTC_COMPARATIVE = "16 CFR 14.15"
CAP_SUBSTANTIATION = "CAP Code 3.7"
CAP_COMPARISONS = "CAP Code 3.32"
CAP_IDENTIFIABLE = "CAP Code 2.1"
ASA_HEALTHY_DOG = "ASA A26-1337640"
ASA_HOTPOINT = "ASA G26-1344778"

# Which rule a claim kind falls under, and the precedent whose claim shape matches.
RULES: dict[str, dict[str, Any]] = {
    # The advertiser's own claims: section 5 and the substantiation doctrine, not the Endorsement Guides.
    "efficacy":                 {"us": [FTC_ACT_5, FTC_SUBSTANTIATION], "uk": [CAP_SUBSTANTIATION, f"{ASA_HEALTHY_DOG} (CAP 3.1, 3.7)"],
                                 "why": "an efficacy claim needs a reasonable basis (competent and reliable evidence) on file before it runs"},
    "health":                   {"us": [FTC_ACT_5, FTC_SUBSTANTIATION], "uk": [CAP_SUBSTANTIATION, f"{ASA_HEALTHY_DOG} (CAP 3.7, 12.11)"],
                                 "why": "a health claim needs substantiation on file; on a drug or OTC product (a cavity or decay claim on "
                                        "toothpaste, 21 CFR 355) it is an OTC drug claim under FDA jurisdiction as well"},
    "comparative":              {"us": [FTC_ACT_5, FTC_SUBSTANTIATION, FTC_COMPARATIVE],
                                 "uk": [CAP_SUBSTANTIATION, CAP_COMPARISONS, f"{ASA_HOTPOINT} (CAP 3.1, 3.3, 3.32)"],
                                 "why": "a comparison with a competitor needs its basis substantiated and, in the UK, clear on the same screen"},
    "superlative":              {"us": [FTC_ACT_5, FTC_SUBSTANTIATION], "uk": [CAP_SUBSTANTIATION, f"{ASA_HOTPOINT} (CAP 3.1, 3.3)"],
                                 "why": "a superlative is a comparison with every competitor and needs its basis"},
    # Endorsements: the Endorsement Guides, 16 CFR Part 255.
    "consumer_testimonial":     {"us": ["16 CFR 255.2(a)", "16 CFR 255.2(b)"], "uk": [f"{ASA_HEALTHY_DOG} (CAP 3.7)"],
                                 "why": "a testimonial must reflect what consumers can generally expect, or disclose it does not"},
    "expert_endorsement":       {"us": ["16 CFR 255.3"], "uk": [f"{ASA_HEALTHY_DOG} (CAP 3.7)"],
                                 "why": "an expert endorsement must be supported by an actual exercise of that expertise"},
    "organization_endorsement": {"us": ["16 CFR 255.4"], "uk": [],
                                 "why": "an organization endorsement must reflect the collective judgment of the organization"},
    "material_connection":      {"us": ["16 CFR 255.5"], "uk": [CAP_IDENTIFIABLE],
                                 "why": "a paid, employment, family or business connection between endorser and advertiser that the audience "
                                        "would not expect must be disclosed clearly and conspicuously; a study does not lift this, a disclosure does"},
}
# Kinds a study cannot lift: the fix is a disclosure in the asset, not paperwork beside it.
NOT_LIFTED_BY_SUBSTANTIATION = {"material_connection"}
ADVISORY_KINDS = {"price", "puffery", "other"}
ADVISORY_WHY = {
    "puffery": "puffery, not a factual claim (FTC does not require substantiation for puffery)",
    "price": "price claim, not read by this gate (FTC Guides Against Deceptive Pricing 16 CFR 233, CAP Code 3.17 to 3.22)",
    "other": "slogan or statement with no factual content",
}
PASS_RULE_IDS = ["16 CFR 255.1", FTC_ACT_5, CAP_SUBSTANTIATION]


def normalize_quote(quote: Any) -> str:
    """Lower, one space between words, no surrounding quotes, no trailing sentence punctuation."""
    s = re.sub(r"\s+", " ", str(quote)).strip().lower()
    s = s.strip("\"'“”‘’")
    return s.rstrip(".!;:, ")


def _read_gcs_text(gcs_uri: str) -> str | None:
    """The object's text, or None when the object does not exist. Any other failure raises: a
    substantiation that cannot be read is an instrument error, not a missing study."""
    from google.api_core.exceptions import NotFound

    from airlock.assets import _storage_client

    bucket_name, _, blob_name = gcs_uri.removeprefix("gs://").partition("/")
    try:
        return _storage_client().bucket(bucket_name).blob(blob_name).download_as_text()
    except NotFound:
        return None


def locate_substantiation(asset: Asset, read_gcs=_read_gcs_text) -> tuple[dict[str, Any], str | None]:
    """Evidence on file for this asset, and where it was read from (None when nowhere).

    Lookup order: <path>.substantiation.yaml when the asset has a local file, else
    <gcs_uri>.substantiation.yaml in the bucket, else nothing. The pipeline builds GCS-only assets
    (path ""), so the bucket is the path that runs in the cloud.
    """
    if asset.path:
        p = pathlib.Path(f"{asset.path}.substantiation.yaml")
        if p.exists():
            return yaml.safe_load(p.read_text()) or {}, str(p)
    if asset.gcs_uri:
        uri = f"{asset.gcs_uri}.substantiation.yaml"
        text = read_gcs(uri)
        if text:
            return yaml.safe_load(text) or {}, uri
    return {}, None


def extract_claims(asset: Asset) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    answer, usage = ask_json(CLAIM_MODEL, [video_part(asset.path, asset.gcs_uri, asset.mime_type), PROMPT], CLAIM_SCHEMA)
    return answer.get("claims", []), {"summary": answer.get("summary", "")}, usage


def _study_name(value: Any) -> str:
    return str(value.get("study") or value) if isinstance(value, dict) else str(value)


def decide(claims: list[dict[str, Any]], substantiation: dict[str, Any]) -> GateResult:
    """The deterministic rule, unit-tested without a model."""
    proven = {normalize_quote(k): v for k, v in (substantiation.get("claims") or {}).items()}
    blocking: list[dict[str, Any]] = []
    advisory: list[dict[str, Any]] = []
    rule_ids: list[str] = []
    substantiated: list[str] = []
    for c in claims:
        kind = c.get("kind", "other")
        row = {"start_s": c.get("start_s"), "end_s": c.get("end_s"), "channel": c.get("channel"), "quote": c.get("quote"),
               "kind": kind, "endorser": c.get("endorser")}
        if kind in ADVISORY_KINDS:
            row["why"] = ADVISORY_WHY[kind]
            advisory.append(row)
            continue
        rule = RULES[kind]
        row["rules"] = rule["us"] + rule["uk"]
        row["why"] = rule["why"]
        key = normalize_quote(c.get("quote", ""))
        if kind not in NOT_LIFTED_BY_SUBSTANTIATION and key in proven:
            row["substantiated_by"] = proven[key]
            substantiated.append(_study_name(proven[key]))
            advisory.append(row)
            continue
        blocking.append(row)
        for r in row["rules"]:
            if r not in rule_ids:
                rule_ids.append(r)
    evidence = [{"blocking_claims": blocking, "advisory_claims": advisory, "claims_total": len(claims),
                 "substantiation_entries": len(proven)}]
    if blocking:
        first = blocking[0]
        reasons = [f"{len(blocking)} regulated claim(s) with no substantiation on file; first at {first['start_s']}s: "
                   f"\"{first['quote']}\" ({first['kind']}, {first['rules'][0]}): {first['why']}"]
        return GateResult(gate="claim", status="BLOCK", reasons=reasons, evidence=evidence, rule_ids=rule_ids, source_of_truth=SOURCE_OF_TRUTH)
    reason = f"no regulated claim without substantiation ({len(claims)} claim(s) read, {len(advisory)} advisory)"
    if substantiated:
        reason += "; substantiation on file: " + "; ".join(dict.fromkeys(substantiated))
    return GateResult(gate="claim", status="PASS", reasons=[reason], evidence=evidence, rule_ids=list(PASS_RULE_IDS), source_of_truth=SOURCE_OF_TRUTH)


def check(asset: Asset) -> GateResult:
    claims, extra, usage = extract_claims(asset)
    substantiation, read_from = locate_substantiation(asset)
    result = decide(claims, substantiation)
    result.evidence.append({"model": usage, "substantiation_read_from": read_from, **extra})
    return result
