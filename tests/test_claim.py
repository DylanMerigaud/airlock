import pytest

from airlock.gates.base import Asset
from airlock.gates.claim import (
    ADVISORY_KINDS,
    CAP_COMPARISONS,
    CAP_SUBSTANTIATION,
    CLAIM_SCHEMA,
    FTC_ACT_5,
    FTC_COMPARATIVE,
    FTC_SUBSTANTIATION,
    RULES,
    decide,
    locate_substantiation,
    normalize_quote,
)


def claim(quote, kind, start=1.0, endorser=None, channel="spoken"):
    return {"start_s": start, "end_s": start + 2, "channel": channel, "quote": quote, "kind": kind, "endorser": endorser}


def test_regulated_claim_without_substantiation_blocks():
    claims = [claim("More dentists recommend Crest than all other toothpastes combined.", "expert_endorsement", 34.4, "dentists")]
    r = decide(claims, {})
    assert r.status == "BLOCK"
    assert "16 CFR 255.3" in r.rule_ids
    assert "34.4s" in r.reasons[0]


def test_slogan_only_passes():
    claims = [claim("Clear as morning.", "other", channel="on_screen_text")]
    r = decide(claims, {})
    assert r.status == "PASS"
    assert r.evidence[0]["advisory_claims"][0]["quote"] == "Clear as morning."


def test_substantiated_claim_is_advisory_not_blocking():
    claims = [claim("Reduces cavities by 21%.", "efficacy")]
    subst = {"claims": {"Reduces cavities by 21%.": "study X, 1960, on file"}}
    r = decide(claims, subst)
    assert r.status == "PASS"
    assert r.evidence[0]["advisory_claims"][0]["substantiated_by"] == "study X, 1960, on file"
    assert "substantiation on file: study X, 1960, on file" in r.reasons[0]


def test_a_study_filed_for_a_different_kind_of_claim_does_not_lift_this_one():
    """A studio's study for an expert endorsement must not silently substantiate an efficacy claim that
    happens to share the same quote text (found live, 2026-09-05: kind was never checked)."""
    claims = [claim("Reduces cavities by 21%.", "efficacy")]
    subst = {"claims": {"Reduces cavities by 21%.": {"study": "an unrelated endorsement study", "kind": "expert_endorsement"}}}
    r = decide(claims, subst)
    assert r.status == "BLOCK"
    assert "filed for a expert_endorsement claim, not efficacy" in r.evidence[0]["blocking_claims"][0]["why"]


def test_a_study_with_no_declared_kind_still_lifts_the_claim():
    """A hand-written substantiation file need not name a kind; presence alone still lifts, as before."""
    claims = [claim("Reduces cavities by 21%.", "efficacy")]
    subst = {"claims": {"Reduces cavities by 21%.": {"study": "study X, no kind field"}}}
    r = decide(claims, subst)
    assert r.status == "PASS"


def test_a_study_whose_kind_matches_lifts_normally():
    claims = [claim("Recommended by 9 out of 10 sommeliers.", "expert_endorsement", endorser="sommeliers")]
    subst = {"claims": {"Recommended by 9 out of 10 sommeliers.": {"study": "the sommelier panel", "kind": "expert_endorsement"}}}
    r = decide(claims, subst)
    assert r.status == "PASS"
    assert r.evidence[0]["advisory_claims"][0]["substantiated_by"]["study"] == "the sommelier panel"


def test_substantiation_matches_on_normalized_quote():
    """The KeyError of 2026-09-05: membership was tested on the lowercased key, the dict indexed with the raw quote."""
    claims = [claim("  reduces   cavities by 21%. ", "efficacy")]
    subst = {"claims": {"Reduces cavities by 21%.": "study X"}}
    r = decide(claims, subst)
    assert r.status == "PASS"
    assert r.evidence[0]["advisory_claims"][0]["substantiated_by"] == "study X"


def test_substantiation_ignores_trailing_punctuation_and_quotes():
    assert normalize_quote('"Recommended by 9 out of 10 sommeliers"') == normalize_quote("Recommended by 9 out of 10 sommeliers.")
    claims = [claim("Recommended by 9 out of 10 sommeliers", "expert_endorsement", endorser="sommeliers")]
    r = decide(claims, {"claims": {"Recommended by 9 out of 10 sommeliers.": {"study": "panel S, 2026"}}})
    assert r.status == "PASS"
    assert "substantiation on file: panel S, 2026" in r.reasons[0]


def test_every_regulated_kind_has_a_rule():
    kinds = set(CLAIM_SCHEMA["properties"]["claims"]["items"]["properties"]["kind"]["enum"])
    assert kinds == set(RULES) | ADVISORY_KINDS


def test_own_claims_cite_section_5_not_the_endorsement_guides():
    for kind in ("efficacy", "health", "comparative", "superlative"):
        r = decide([claim("x", kind)], {})
        assert r.status == "BLOCK"
        assert FTC_ACT_5 in r.rule_ids and FTC_SUBSTANTIATION in r.rule_ids and CAP_SUBSTANTIATION in r.rule_ids, kind
        assert not any(x.startswith("16 CFR 255") for x in r.rule_ids), (kind, r.rule_ids)


def test_endorsement_kinds_keep_part_255():
    assert "16 CFR 255.2(a)" in decide([claim("x", "consumer_testimonial")], {}).rule_ids
    assert "16 CFR 255.3" in decide([claim("x", "expert_endorsement")], {}).rule_ids
    assert "16 CFR 255.4" in decide([claim("x", "organization_endorsement")], {}).rule_ids


def test_comparative_adds_the_comparative_advertising_rules():
    r = decide([claim("21% fewer cavities than the leading brand", "comparative")], {})
    assert FTC_COMPARATIVE in r.rule_ids and CAP_COMPARISONS in r.rule_ids


def test_health_claim_names_the_fda_jurisdiction():
    r = decide([claim("Crest stops cavities", "health", 5.0)], {})
    assert r.status == "BLOCK"
    assert "FDA" in r.reasons[0] and "OTC" in r.reasons[0]


def test_puffery_is_advisory_with_the_ftc_reason():
    r = decide([claim("It's the newest, most exciting sound in town", "puffery")], {})
    assert r.status == "PASS"
    row = r.evidence[0]["advisory_claims"][0]
    assert row["why"] == "puffery, not a factual claim (FTC does not require substantiation for puffery)"


def test_material_connection_blocks_on_255_5_and_a_study_does_not_lift_it():
    c = claim("I use it every day and I love it", "material_connection", 3.0, endorser="an employee presented as a customer")
    r = decide([c], {})
    assert r.status == "BLOCK"
    assert "16 CFR 255.5" in r.rule_ids
    r2 = decide([c], {"claims": {"I use it every day and I love it": "internal survey"}})
    assert r2.status == "BLOCK", "a disclosure lifts a 255.5 block, a study does not"


def test_substantiation_lookup_reads_the_bucket_for_gcs_only_assets():
    seen = []

    def fake_gcs(uri):
        seen.append(uri)
        return "claims:\n  'Recommended by 9 out of 10 sommeliers.': panel S\n"

    subst, read_from = locate_substantiation(Asset(asset_id="x", path="", gcs_uri="gs://b/x.mp4"), read_gcs=fake_gcs)
    assert seen == ["gs://b/x.mp4.substantiation.yaml"]
    assert read_from == "gs://b/x.mp4.substantiation.yaml"
    assert subst["claims"]["Recommended by 9 out of 10 sommeliers."] == "panel S"


def test_substantiation_lookup_is_empty_when_the_object_is_absent():
    assert locate_substantiation(Asset(asset_id="x", path="", gcs_uri="gs://b/x.mp4"), lambda uri: None)[0] == {}


def test_substantiation_lookup_prefers_the_local_file(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    (tmp_path / "clip.mp4.substantiation.yaml").write_text("claims:\n  'A': local study\n")

    def never(uri):
        raise AssertionError("the bucket must not be read when the local file exists")

    subst, read_from = locate_substantiation(Asset(asset_id="x", path=str(clip), gcs_uri="gs://b/clip.mp4"), read_gcs=never)
    assert subst["claims"]["A"] == "local study"
    assert read_from == str(tmp_path / "clip.mp4.substantiation.yaml")


def test_substantiation_lookup_falls_back_to_the_bucket_when_no_local_file(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    subst, read_from = locate_substantiation(Asset(asset_id="x", path=str(clip), gcs_uri="gs://b/clip.mp4"),
                                             read_gcs=lambda uri: "claims:\n  'A': bucket study\n")
    assert subst["claims"]["A"] == "bucket study"
    assert read_from == "gs://b/clip.mp4.substantiation.yaml"


def test_substantiation_read_failure_is_not_a_missing_study():
    def broken(uri):
        raise PermissionError("403 on the bucket")

    with pytest.raises(PermissionError):
        locate_substantiation(Asset(asset_id="x", path="", gcs_uri="gs://b/x.mp4"), broken)
