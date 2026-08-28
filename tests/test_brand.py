from airlock.gates.brand import decide, load_charter

CHARTER = load_charter()


def base_findings(**over):
    f = {"wordmark_seen": True, "wordmark_timestamps_s": [2.0], "on_screen_text": ["Nimbus", "Clear as morning."],
         "dominant_colors_hex": ["#F4F1EA", "#1F4E79"], "tone_words": ["calm", "premium"], "exclusion_violations": [], "other_brands_seen": []}
    f.update(over)
    return f


def test_clean_asset_passes():
    r = decide(base_findings(), CHARTER)
    assert r.status == "PASS"


def test_missing_wordmark_blocks():
    r = decide(base_findings(wordmark_seen=False), CHARTER)
    assert r.status == "BLOCK"
    assert "charter:mandatory_mentions" in r.rule_ids


def test_health_claim_exclusion_blocks():
    r = decide(base_findings(exclusion_violations=[{"exclusion": "no health or medical claim of any kind", "evidence": "Doctors recommend Nimbus for better sleep", "start_s": 3.0}]), CHARTER)
    assert r.status == "BLOCK"
    assert "Doctors recommend" in r.reasons[0]


def test_forbidden_colour_and_other_brand_block():
    r = decide(base_findings(dominant_colors_hex=["#FE0000"], other_brands_seen=["Crest"]), CHARTER)
    assert r.status == "BLOCK"
    assert any("forbidden palette" in x for x in r.reasons)
    assert any("Crest" in x for x in r.reasons)
