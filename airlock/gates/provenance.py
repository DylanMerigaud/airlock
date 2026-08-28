"""Provenance gate: is there a C2PA manifest, and does its signature verify?

A cryptographic check, not a model's opinion. The reader is c2pa-python (the c2pa-rs library).
Three outcomes:
  no manifest            -> BLOCK, reason "no C2PA manifest"
  manifest, invalid      -> BLOCK, reason names the failed validation codes
  manifest, valid        -> PASS, evidence carries the issuer, the claim generator and the assertions
"""

from __future__ import annotations

import json
from typing import Any

from airlock.gates.base import Asset, GateResult

SOURCE_OF_TRUTH = "C2PA manifest (c2pa-python, cryptographic verification)"
RULE_MANIFEST_REQUIRED = "airlock:provenance:manifest-required"
RULE_SIGNATURE_VALID = "airlock:provenance:signature-valid"


def read_manifest_store(path: str) -> dict[str, Any] | None:
    """Return the manifest store as a dict, or None when the file carries no manifest."""
    import c2pa

    try:
        reader = c2pa.Reader(path)
    except Exception as exc:  # c2pa raises a ManifestNotFound subclass with 'no JUMBF data found'
        if "ManifestNotFound" in type(exc).__name__ or "no JUMBF" in str(exc) or "not found" in str(exc).lower():
            return None
        raise
    with reader:
        return json.loads(reader.json())


def summarize(store: dict[str, Any]) -> dict[str, Any]:
    active = store.get("active_manifest")
    manifest = (store.get("manifests") or {}).get(active, {}) if active else {}
    sig = manifest.get("signature_info") or {}
    results = store.get("validation_results") or {}
    active_res = results.get("activeManifest") or results.get("active_manifest") or {}
    failures = [f for f in (active_res.get("failure") or [])]
    successes = [s.get("code") for s in (active_res.get("success") or [])]
    return {
        "active_manifest": active,
        "validation_state": store.get("validation_state"),
        "claim_generator": manifest.get("claim_generator") or (manifest.get("claim_generator_info") or [{}])[0].get("name"),
        "issuer": sig.get("issuer"),
        "cert_serial": sig.get("cert_serial_number"),
        "signing_time": sig.get("time"),
        "assertions": [a.get("label") for a in manifest.get("assertions", [])],
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
    if s["failure_codes"] or state == "invalid":
        return GateResult(gate="provenance", status="BLOCK",
                          reasons=[f"C2PA manifest present but validation failed: {', '.join(s['failure_codes']) or state}"],
                          evidence=[s], rule_ids=[RULE_SIGNATURE_VALID], source_of_truth=SOURCE_OF_TRUTH)
    reason = f"C2PA manifest verified ({s.get('validation_state') or 'valid'}); signed by {s.get('issuer') or 'unknown issuer'}"
    return GateResult(gate="provenance", status="PASS", reasons=[reason], evidence=[s],
                      rule_ids=[RULE_MANIFEST_REQUIRED, RULE_SIGNATURE_VALID], source_of_truth=SOURCE_OF_TRUTH)


def check(asset: Asset) -> GateResult:
    return decide(read_manifest_store(asset.path))
