import os

import pytest

from airlock.gates.base import Asset
from airlock.gates.provenance import decide, read_manifest_store

CREST = os.path.join(os.path.dirname(__file__), "..", "assets", "real", "CrestToothpa.mp4")


def test_no_manifest_blocks():
    r = decide(None)
    assert r.status == "BLOCK"
    assert "no C2PA manifest" in r.reasons[0]
    assert r.rule_ids == ["airlock:provenance:manifest-required"]


def test_invalid_signature_blocks():
    store = {
        "active_manifest": "urn:x",
        "validation_state": "Invalid",
        "manifests": {"urn:x": {"claim_generator": "test", "signature_info": {"issuer": "Nobody"}, "assertions": []}},
        "validation_results": {"activeManifest": {"failure": [{"code": "assertion.bmffHash.mismatch", "explanation": "x"}], "success": []}},
    }
    r = decide(store)
    assert r.status == "BLOCK"
    assert "assertion.bmffHash.mismatch" in r.reasons[0]
    assert r.rule_ids == ["airlock:provenance:signature-valid"]


def test_valid_but_untrusted_signer_blocks():
    store = {
        "active_manifest": "urn:x",
        "validation_state": "Valid",
        "manifests": {"urn:x": {"claim_generator": "c2patool", "signature_info": {"issuer": "Somebody"}, "assertions": []}},
        "validation_results": {"activeManifest": {"failure": [{"code": "signingCredential.untrusted", "explanation": "x"}], "success": [{"code": "claimSignature.validated"}]}},
    }
    r = decide(store)
    assert r.status == "BLOCK"
    assert r.rule_ids == ["airlock:provenance:signer-trusted"]
    assert "Somebody" in r.reasons[0]


def test_trusted_manifest_passes():
    store = {
        "active_manifest": "urn:x",
        "validation_state": "Trusted",
        "manifests": {"urn:x": {"claim_generator": "c2patool", "signature_info": {"issuer": "Airlock test CA"}, "assertions": [{"label": "c2pa.actions"}]}},
        "validation_results": {"activeManifest": {"failure": [], "success": [{"code": "signingCredential.trusted"}, {"code": "claimSignature.validated"}]}},
    }
    r = decide(store)
    assert r.status == "PASS"
    assert "Airlock test CA" in r.reasons[0]
    assert r.evidence[0]["assertions"] == ["c2pa.actions"]


@pytest.mark.skipif(not os.path.exists(CREST), reason="run scripts/fetch_assets.sh first")
def test_crest_film_has_no_manifest():
    assert read_manifest_store(CREST) is None
    assert decide(read_manifest_store(CREST)).status == "BLOCK"


SYN = os.path.join(os.path.dirname(__file__), "..", "assets", "synthetic", "nimbus-test-clip.mp4")


@pytest.mark.skipif(not os.path.exists(SYN), reason="run scripts/make_synthetic_asset.sh first")
def test_signed_synthetic_clip_is_trusted():
    r = decide(read_manifest_store(SYN))
    assert r.status == "PASS", r.reasons
    assert r.evidence[0]["validation_state"] == "Trusted"
