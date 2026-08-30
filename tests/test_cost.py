from airlock.cost import estimate, load_pricing

P = load_pricing()


def test_claim_gate_cost_from_tokens():
    u = estimate("claim", [{"blocking_claims": []}, {"model": {"model": "gemini-2.5-pro", "prompt_tokens": 17164, "output_tokens": 763}}], P)
    assert u.tokens_in == 17164 and u.tokens_out == 763
    assert abs(u.cost_usd - (17164 * 1.25e-6 + 763 * 1e-5)) < 1e-9
    assert "gemini-2.5-pro" in u.basis


def test_rights_gate_cost_per_started_minute_and_feature():
    u = estimate("rights", [{"findings": [], "features": ["logo", "face", "text", "explicit"], "duration_s": 30.0}], P)
    assert u.video_minutes == 1 and u.features == 4
    assert abs(u.cost_usd - (0.15 + 0.10 + 0.15 + 0.10)) < 1e-9


def test_provenance_costs_nothing():
    u = estimate("provenance", [{"manifest": None}], P)
    assert u.cost_usd == 0.0 and u.tokens_in == 0


def test_pricing_file_is_dated_and_cites_skus():
    assert P["read_on"] == "2026-08-29" and P["currency"] == "USD"
    assert P["video_intelligence"]["free_minutes_per_feature_per_month"] == 1000


def test_run_cost_says_not_measured_when_no_gate_priced_itself():
    from agents.pipeline.agent import run_cost

    out = run_cost({"rights": {"usage": {"cost_usd": None, "error": "FileNotFoundError: pricing.yaml not found"}}, "claim": {"usage": {}}})
    assert out["cost_usd"] is None and out["per_gate"] == {}
    assert out["basis"].startswith("not measured")


def test_run_cost_sums_the_gates():
    from agents.pipeline.agent import run_cost

    out = run_cost({"rights": {"usage": {"cost_usd": 0.5, "tokens_in": 0, "tokens_out": 0, "video_minutes": 1.0}},
                    "claim": {"usage": {"cost_usd": 0.029, "tokens_in": 17164, "tokens_out": 763, "video_minutes": 0}}})
    assert abs(out["cost_usd"] - 0.529) < 1e-9 and out["tokens_in"] == 17164 and out["video_minutes"] == 1.0
