"""Provenance gate: is there a C2PA manifest, does its signature verify, and does the manifest say
the content is generated?

A cryptographic check, not a model's opinion. The reader is c2pa-python (the c2pa-rs library).
Outcomes:
  no manifest            -> BLOCK, reason "no C2PA manifest"
  manifest, invalid      -> BLOCK, reason names the failed validation codes
  manifest, untrusted    -> BLOCK, the signer is not on trust/trust-anchors.pem
  manifest, trusted      -> PASS; the evidence carries the issuer, the claim generator, the assertions
                            and the actions' digitalSourceType. trainedAlgorithmicMedia (or the
                            composite form) is the machine-readable "generated" marking the EU AI Act
                            Article 50 asks for; a trusted manifest without it still PASSes, with an
                            advisory reason saying the marking is absent.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from airlock.gates.base import Asset, GateResult

SOURCE_OF_TRUTH = "C2PA manifest (c2pa-python, cryptographic verification against trust/trust-anchors.pem)"
RULE_MANIFEST_REQUIRED = "airlock:provenance:manifest-required"
RULE_SIGNATURE_VALID = "airlock:provenance:signature-valid"
RULE_SIGNER_TRUSTED = "airlock:provenance:signer-trusted"
RULE_GENERATED_MARKING = "airlock:provenance:generated-marking"
# IPTC digital source types that mean "made by a trained model" (the c2pa.actions digitalSourceType values).
GENERATED_SOURCE_TYPES = ("trainedAlgorithmicMedia", "compositeWithTrainedAlgorithmicMedia")
ADVISORY_NO_MARKING = "no machine-readable generated-content marking in the manifest (EU AI Act Article 50)"
TRUST_ANCHORS = pathlib.Path(__file__).resolve().parents[2] / "trust" / "trust-anchors.pem"


def reader_context(trust_pem: pathlib.Path = TRUST_ANCHORS):
    """A c2pa Context whose allowed list is the studio's own signing certificates.

    Without it a self-issued signer validates as Valid with signingCredential.untrusted in the
    failures (measured 2026-08-28 on c2pa-rs 0.90.16); with it the state is Trusted.
    """
    import c2pa

    trust: dict[str, Any] = {}
    if trust_pem.exists():
        trust["allowed_list"] = trust_pem.read_text()
    settings = c2pa.Settings.from_dict({"trust": trust, "verify": {"verify_trust": True}})
    return c2pa.ContextBuilder().with_settings(settings).build()


def read_manifest_store(path: str) -> dict[str, Any] | None:
    """Return the manifest store as a dict, or None when the file carries no manifest."""
    import c2pa

    try:
        reader = c2pa.Reader(path, context=reader_context())
    except Exception as exc:  # c2pa raises a ManifestNotFound subclass with 'no JUMBF data found'
        if "ManifestNotFound" in type(exc).__name__ or "no JUMBF" in str(exc) or "not found" in str(exc).lower():
            return None
        raise
    with reader:
        return json.loads(reader.json())


def actions_of(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """The c2pa.actions (v1 or v2) entries: action, digitalSourceType, softwareAgent name."""
    out: list[dict[str, Any]] = []
    for a in manifest.get("assertions", []):
        if not str(a.get("label", "")).startswith("c2pa.actions"):
            continue
        for act in (a.get("data") or {}).get("actions") or []:
            agent = act.get("softwareAgent")
            out.append({"action": act.get("action"), "digitalSourceType": act.get("digitalSourceType"),
                        "softwareAgent": agent.get("name") if isinstance(agent, dict) else agent})
    return out


def generated_marking(actions: list[dict[str, Any]]) -> str | None:
    """The digitalSourceType that marks the content as generated, or None when no action carries one."""
    for act in actions:
        t = str(act.get("digitalSourceType") or "")
        if t.rsplit("/", 1)[-1] in GENERATED_SOURCE_TYPES:
            return t
    return None


def summarize(store: dict[str, Any]) -> dict[str, Any]:
    active = store.get("active_manifest")
    manifest = (store.get("manifests") or {}).get(active, {}) if active else {}
    sig = manifest.get("signature_info") or {}
    results = store.get("validation_results") or {}
    active_res = results.get("activeManifest") or results.get("active_manifest") or {}
    failures = [f for f in (active_res.get("failure") or [])]
    successes = [s.get("code") for s in (active_res.get("success") or [])]
    actions = actions_of(manifest)
    marking = generated_marking(actions)
    return {
        "active_manifest": active,
        "validation_state": store.get("validation_state"),
        "claim_generator": manifest.get("claim_generator") or (manifest.get("claim_generator_info") or [{}])[0].get("name"),
        "issuer": sig.get("issuer"),
        "cert_serial": sig.get("cert_serial_number"),
        "signing_time": sig.get("time"),
        "assertions": [a.get("label") for a in manifest.get("assertions", [])],
        "actions": actions,
        "generated_marking": marking,
        "marked_generated": marking is not None,
        "ingredients": len(manifest.get("ingredients", [])),
        "failure_codes": [f.get("code") for f in failures],
        "failure_explanations": [f.get("explanation") for f in failures][:5],
        "success_codes": successes[:12],
    }


def decide(store: dict[str, Any] | None) -> GateResult:
    """The deterministic rule, unit-tested without a file."""
    if store is None:
        return GateResult(gate="provenance", status="BLOCK", reasons=["no C2PA manifest in the asset"],
                          evidence=[{"manifest": None}], rule_ids=[RULE_MANIFEST_REQUIRED], source_of_truth=SOURCE_OF_TRUTH)
    s = summarize(store)
    state = (s.get("validation_state") or "").lower()
    untrusted = [c for c in s["failure_codes"] if c.startswith("signingCredential")]
    other = [c for c in s["failure_codes"] if not c.startswith("signingCredential")]
    if other or state == "invalid":
        return GateResult(gate="provenance", status="BLOCK",
                          reasons=[f"C2PA manifest present but validation failed: {', '.join(other) or state}"],
                          evidence=[s], rule_ids=[RULE_SIGNATURE_VALID], source_of_truth=SOURCE_OF_TRUTH)
    if untrusted or state != "trusted":
        return GateResult(gate="provenance", status="BLOCK",
                          reasons=[f"C2PA signature valid but the signer is not on the trust list: {s.get('issuer') or 'unknown issuer'} "
                                   f"({', '.join(untrusted) or state})"],
                          evidence=[s], rule_ids=[RULE_SIGNER_TRUSTED], source_of_truth=SOURCE_OF_TRUTH)
    reason = f"C2PA manifest verified and trusted; signed by {s.get('issuer')}; created by {s.get('claim_generator')}"
    rule_ids = [RULE_MANIFEST_REQUIRED, RULE_SIGNATURE_VALID, RULE_SIGNER_TRUSTED]
    reasons = [reason]
    if s["marked_generated"]:
        short = str(s["generated_marking"]).rsplit("/", 1)[-1]
        reasons[0] += f"; marked as generated (digitalSourceType {short}, the EU AI Act Article 50 machine-readable marking)"
        rule_ids.append(RULE_GENERATED_MARKING)
    else:
        reasons.append(f"advisory: {ADVISORY_NO_MARKING}")
        s["advisory"] = [ADVISORY_NO_MARKING]
    return GateResult(gate="provenance", status="PASS", reasons=reasons, evidence=[s], rule_ids=rule_ids, source_of_truth=SOURCE_OF_TRUTH)


def check(asset: Asset) -> GateResult:
    from airlock.assets import ensure_local

    return decide(read_manifest_store(ensure_local(asset).path))
