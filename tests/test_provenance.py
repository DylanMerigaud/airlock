import os

import pytest

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
        "validation_results": {"activeManifest": {"failure": [{"code": "signingCredential.untrusted", "explanation": "x"}],
                                                  "success": [{"code": "claimSignature.validated"}]}},
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


def _trusted(assertions):
    return {
        "active_manifest": "urn:x",
        "validation_state": "Trusted",
        "manifests": {"urn:x": {"claim_generator": "c2patool", "signature_info": {"issuer": "Airlock test CA"}, "assertions": assertions}},
        "validation_results": {"activeManifest": {"failure": [], "success": [{"code": "signingCredential.trusted"}, {"code": "claimSignature.validated"}]}},
    }


GENERATED = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
NO_MARKING = "no machine-readable generated-content marking in the manifest (EU AI Act Article 50)"


def test_trusted_manifest_with_generated_marking_names_it():
    store = _trusted([{"label": "c2pa.actions.v2", "data": {"actions": [
        {"action": "c2pa.created", "digitalSourceType": GENERATED, "softwareAgent": {"name": "Veo 3.1 on Vertex AI"}},
        {"action": "c2pa.edited", "softwareAgent": {"name": "ffmpeg drawtext overlay"}}]}}])
    r = decide(store)
    assert r.status == "PASS"
    assert "marked as generated (digitalSourceType trainedAlgorithmicMedia" in r.reasons[0]
    assert "airlock:provenance:generated-marking" in r.rule_ids
    assert len(r.reasons) == 1
    ev = r.evidence[0]
    assert ev["marked_generated"] is True
    assert ev["actions"][0] == {"action": "c2pa.created", "digitalSourceType": GENERATED, "softwareAgent": "Veo 3.1 on Vertex AI"}


def test_trusted_manifest_without_generated_marking_passes_with_an_advisory():
    store = _trusted([{"label": "c2pa.actions", "data": {"actions": [{"action": "c2pa.edited", "softwareAgent": "some editor"}]}}])
    r = decide(store)
    assert r.status == "PASS"
    assert "airlock:provenance:generated-marking" not in r.rule_ids
    assert r.reasons[1] == f"advisory: {NO_MARKING}"
    assert r.evidence[0]["marked_generated"] is False
    assert r.evidence[0]["advisory"] == [NO_MARKING]


def test_composite_generated_marking_counts():
    store = _trusted([{"label": "c2pa.actions.v2", "data": {"actions": [
        {"action": "c2pa.created", "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/compositeWithTrainedAlgorithmicMedia"}]}}])
    assert decide(store).evidence[0]["marked_generated"] is True


def test_untrusted_manifest_is_still_a_block_whatever_the_marking():
    store = _trusted([{"label": "c2pa.actions.v2", "data": {"actions": [{"action": "c2pa.created", "digitalSourceType": GENERATED}]}}])
    store["validation_state"] = "Valid"
    store["validation_results"]["activeManifest"]["failure"] = [{"code": "signingCredential.untrusted", "explanation": "x"}]
    r = decide(store)
    assert r.status == "BLOCK"
    assert r.evidence[0]["marked_generated"] is True


CLEAN = os.path.join(os.path.dirname(__file__), "..", "assets", "synthetic", "calibration", "nimbus-clean-clip.mp4")


@pytest.mark.skipif(not (os.path.exists(SYN) and os.path.exists(CLEAN)), reason="run scripts/fetch_assets.sh first")
def test_shipped_nimbus_clips_carry_the_generated_marking():
    """Measured with c2patool 0.27.16 on 2026-09-05: both signed clips carry c2pa.created with trainedAlgorithmicMedia."""
    for path in (SYN, CLEAN):
        r = decide(read_manifest_store(path))
        assert r.status == "PASS", r.reasons
        assert r.evidence[0]["generated_marking"] == GENERATED
        assert "airlock:provenance:generated-marking" in r.rule_ids
