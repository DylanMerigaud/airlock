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
        "validation_results": {"activeManifest": {"failure": [{"code": "signingCredential.untrusted", "explanation": "x"}], "success": []}},
    }
    r = decide(store)
    assert r.status == "BLOCK"
    assert "signingCredential.untrusted" in r.reasons[0]


def test_valid_manifest_passes():
    store = {
        "active_manifest": "urn:x",
        "validation_state": "Valid",
        "manifests": {"urn:x": {"claim_generator": "c2patool", "signature_info": {"issuer": "Airlock test CA"}, "assertions": [{"label": "c2pa.actions"}]}},
        "validation_results": {"activeManifest": {"failure": [], "success": [{"code": "claimSignature.validated"}]}},
    }
    r = decide(store)
    assert r.status == "PASS"
    assert "Airlock test CA" in r.reasons[0]
    assert r.evidence[0]["assertions"] == ["c2pa.actions"]


@pytest.mark.skipif(not os.path.exists(CREST), reason="run scripts/fetch_assets.sh first")
def test_crest_film_has_no_manifest():
    assert read_manifest_store(CREST) is None
    assert decide(read_manifest_store(CREST)).status == "BLOCK"
