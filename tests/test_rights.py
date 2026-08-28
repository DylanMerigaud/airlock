from airlock.gates.rights import decide, load_registry

REG = load_registry()


def test_not_cleared_logo_and_faces_block():
    ann = {"logos": [{"name": "Crest", "entity_id": "/m/035df5", "spans": [{"start": 34.13, "end": 43.34, "confidence": 0.853}]}],
           "texts": [{"text": "AMERICAN DENTAL ASSOCIATION", "spans": [{"start": 43.7, "end": 51.4}]}],
           "faces": [{"start": 18.5, "end": 28.4}], "explicit_frames": {"VERY_UNLIKELY": 54, "POSSIBLE": 1}}
    r = decide(ann, REG)
    assert r.status == "BLOCK"
    assert any("Crest" in x and "not_cleared" in x for x in r.reasons)
    assert any("face track" in x for x in r.reasons)
    assert "registry:brands:not_cleared" in r.rule_ids
    assert not any("explicit" in x for x in r.reasons)


def test_unknown_brand_in_text_blocks():
    ann = {"logos": [], "texts": [{"text": "Drink Zorbo", "spans": [{"start": 1.0, "end": 2.0}]}], "faces": [], "explicit_frames": {}}
    reg = {"brands": [{"name": "Zorbo", "status": "unknown"}], "faces": {"releases": []}, "policy": {"unknown_brand": "BLOCK", "unknown_face": "BLOCK"}}
    r = decide(ann, reg)
    assert r.status == "BLOCK"
    assert "registry:brands:unknown" in r.rule_ids


def test_cleared_brand_no_faces_passes():
    ann = {"logos": [], "texts": [{"text": "Nimbus", "spans": [{"start": 6.0, "end": 8.0}]}], "faces": [], "explicit_frames": {"VERY_UNLIKELY": 8}}
    r = decide(ann, REG)
    assert r.status == "PASS"
    assert "Nimbus" in r.reasons[0]


def test_explicit_content_blocks_at_threshold():
    ann = {"logos": [], "texts": [], "faces": [], "explicit_frames": {"LIKELY": 2}}
    r = decide(ann, REG)
    assert r.status == "BLOCK"
    assert "registry:explicit_content" in r.rule_ids
