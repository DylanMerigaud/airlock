from airlock.gates.base import Asset
from airlock.gates.rights import asset_refs, brands_in_text, decide, load_registry, releases_for

REG = load_registry()


def test_not_cleared_logo_and_faces_block():
    ann = {"logos": [{"name": "Crest", "entity_id": "/m/035df5", "spans": [{"start": 34.13, "end": 43.34, "confidence": 0.853}]}],
           "texts": [{"text": "AMERICAN DENTAL ASSOCIATION", "spans": [{"start": 43.7, "end": 51.4}]}],
           "faces": [{"start": 18.5, "end": 28.4}], "explicit_frames": {"VERY_UNLIKELY": 54, "POSSIBLE": 1}}
    r = decide(ann, REG)
    assert r.status == "BLOCK"
    assert any("Crest" in x and "not_cleared" in x for x in r.reasons)
    assert any("American Dental Association" in x and "not_cleared" in x for x in r.reasons)
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


def test_unknown_logo_is_named_as_a_guess():
    ann = {"logos": [{"name": "DeLorean Motor Company", "entity_id": "/m/x", "spans": [{"start": 2.0, "end": 9.0, "confidence": 0.91}]}],
           "texts": [], "faces": [], "explicit_frames": {}}
    r = decide(ann, REG)
    assert r.status == "BLOCK"
    assert "registry:brands:unknown" in r.rule_ids
    assert "guess: DeLorean Motor Company" in r.reasons[0]


def test_registry_name_matches_token_wise_across_text_lines():
    """The ADA seal comes back from Video Intelligence as two lines; the entry must still fire."""
    texts = [{"text": "Accepted", "spans": [{"start": 25.6, "end": 30.0}]},
             {"text": "AMERICAN DENTAL", "spans": [{"start": 25.8, "end": 30.0}]},
             {"text": "ASSOCIATION", "spans": [{"start": 26.1, "end": 30.0}]}]
    hits = brands_in_text(texts, REG)
    assert [h["name"] for h in hits] == ["American Dental Association"]
    assert hits[0]["across_lines"] is True and hits[0]["spans"][0]["start"] == 25.8
    r = decide({"logos": [], "texts": texts, "faces": [], "explicit_frames": {}}, REG)
    assert r.status == "BLOCK"
    assert "registry:brands:not_cleared" in r.rule_ids
    assert any("American Dental Association" in x and "across lines" in x for x in r.reasons)


def test_token_match_needs_every_word_within_the_window():
    far = [{"text": "AMERICAN DENTAL", "spans": [{"start": 2.0, "end": 3.0}]}, {"text": "ASSOCIATION", "spans": [{"start": 20.0, "end": 21.0}]}]
    assert brands_in_text(far, REG) == []
    partial = [{"text": "DENTAL ASSOCIATION", "spans": [{"start": 2.0, "end": 3.0}]}]
    assert brands_in_text(partial, REG) == []


def test_single_word_name_matches_whole_words_only():
    assert brands_in_text([{"text": "Crestwood Drive", "spans": [{"start": 1.0, "end": 2.0}]}], REG) == []
    assert [h["name"] for h in brands_in_text([{"text": "NEW CREST WITH FLUORISTAN", "spans": [{"start": 1.0, "end": 2.0}]}], REG)] == ["Crest"]


def test_texts_are_kept_in_the_evidence():
    texts = [{"text": "Nimbus", "spans": [{"start": 6.0, "end": 8.0}]}]
    r = decide({"logos": [], "texts": texts, "faces": [], "explicit_frames": {}}, REG)
    assert r.evidence[0]["texts"] == [{"text": "Nimbus", "start": 6.0}]


FACES = {"logos": [], "texts": [], "faces": [{"start": 0.0, "end": 8.0}, {"start": 2.0, "end": 5.0}], "explicit_frames": {}}


def _reg(releases):
    return {"brands": [], "faces": {"releases": releases}, "policy": {"unknown_brand": "BLOCK", "unknown_face": "BLOCK"}}


def test_release_clears_only_the_asset_it_names():
    reg = _reg([{"asset_id": "spot-a", "signed_by": "the two actors", "date": "2026-09-01"}])
    assert decide(FACES, reg, refs={"spot-a"}).status == "PASS"
    r = decide(FACES, reg, refs={"spot-b"})
    assert r.status == "BLOCK"
    assert "registry:faces:no_release" in r.rule_ids
    assert "for this asset" in r.reasons[0]


def test_release_list_for_another_asset_no_longer_disables_the_face_check():
    """Before 2026-09-05 any non-empty release list cleared every face."""
    reg = _reg([{"asset_id": "someone-elses-spot"}])
    assert decide(FACES, reg, refs={"spot-b"}).status == "BLOCK"
    assert decide(FACES, reg).status == "BLOCK"


def test_blanket_release_covers_all():
    reg = _reg([{"covers": "all", "signed_by": "studio staff"}])
    r = decide(FACES, reg, refs={"anything"})
    assert r.status == "PASS"
    assert "faces released" in r.reasons[0]
    assert r.evidence[0]["findings"][0]["released_by"] == ["all"]


def test_asset_refs_include_the_file_stem_from_path_and_uri():
    a = Asset(asset_id="nimbus-clean-clip-89dcb1549e9d", path="assets/synthetic/calibration/nimbus-clean-clip.mp4",
              gcs_uri="gs://b/calibration/nimbus-clean-clip.mp4")
    assert asset_refs(a) == {"nimbus-clean-clip-89dcb1549e9d", "nimbus-clean-clip"}
    assert releases_for(asset_refs(a), _reg([{"asset_id": "nimbus-clean-clip"}])) != []


def test_registry_has_no_unread_key():
    """Every top-level key of the registry is read by the gate (works.licences was removed for that reason)."""
    assert set(REG) == {"brands", "faces", "policy"}
    assert REG["faces"]["releases"] == []
