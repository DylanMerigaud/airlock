from airlock.gates.claim import decide


def test_regulated_claim_without_substantiation_blocks():
    claims = [{"start_s": 34.4, "end_s": 38.8, "channel": "spoken", "quote": "More dentists recommend Crest than all other toothpastes combined.", "kind": "expert_endorsement", "endorser": "dentists"}]
    r = decide(claims, {})
    assert r.status == "BLOCK"
    assert "16 CFR 255.3" in r.rule_ids
    assert "34.4s" in r.reasons[0]


def test_slogan_only_passes():
    claims = [{"start_s": 1, "end_s": 3, "channel": "on_screen_text", "quote": "Clear as morning.", "kind": "other"}]
    r = decide(claims, {})
    assert r.status == "PASS"
    assert r.evidence[0]["advisory_claims"][0]["quote"] == "Clear as morning."


def test_substantiated_claim_is_advisory_not_blocking():
    claims = [{"start_s": 1, "end_s": 3, "channel": "spoken", "quote": "Reduces cavities by 21%.", "kind": "efficacy"}]
    subst = {"claims": {"Reduces cavities by 21%.": "study X, 1960, on file"}}
    r = decide(claims, subst)
    assert r.status == "PASS"
    assert r.evidence[0]["advisory_claims"][0]["substantiated_by"] == "study X, 1960, on file"


def test_every_regulated_kind_has_a_rule():
    from airlock.gates.claim import CLAIM_SCHEMA, RULES, ADVISORY_KINDS

    kinds = set(CLAIM_SCHEMA["properties"]["claims"]["items"]["properties"]["kind"]["enum"])
    assert kinds == set(RULES) | ADVISORY_KINDS


def test_substantiation_lookup_tolerates_gcs_only_asset():
    from airlock.gates.base import Asset
    from airlock.gates.claim import load_substantiation

    assert load_substantiation(Asset(asset_id="x", path="", gcs_uri="gs://b/x.mp4")) == {}
