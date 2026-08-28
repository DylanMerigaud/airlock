from airlock.verdict import GateHealth, decide, promql_questions

GATES = ["rights", "claim", "brand", "provenance"]


def ok(gate, **over):
    return {"gate": gate, "status": over.get("status", "PASS"), "reasons": over.get("reasons", ["fine"]), "rule_ids": over.get("rule_ids", [])}


def healthy(gate, **over):
    return GateHealth(gate, error_rate_15m=over.get("err", 0.0), seconds_since_success=over.get("age", 30.0), calibration_catches_7d=over.get("catches", 3.0))


def test_all_pass_healthy_calibrated_is_pass():
    v = decide({g: ok(g) for g in GATES}, {g: healthy(g) for g in GATES})
    assert v.status == "PASS" and not v.needs_human


def test_paperwork_block_needs_a_human():
    results = {g: ok(g) for g in GATES}
    results["claim"] = ok("claim", status="BLOCK", reasons=["1 regulated claim"], rule_ids=["16 CFR 255.3"])
    v = decide(results, {g: healthy(g) for g in GATES})
    assert v.status == "BLOCK" and v.motive == "content" and v.needs_human
    assert "16 CFR 255.3" in v.rule_ids


def test_asset_defect_block_needs_no_human():
    results = {g: ok(g) for g in GATES}
    results["provenance"] = ok("provenance", status="BLOCK", reasons=["broken"], rule_ids=["airlock:provenance:signature-valid"])
    results["brand"] = ok("brand", status="BLOCK", reasons=["red"], rule_ids=["charter:palette"])
    v = decide(results, {g: healthy(g) for g in GATES})
    assert v.status == "BLOCK" and v.motive == "content" and not v.needs_human


def test_stale_gate_is_control_unavailable_and_needs_human():
    health = {g: healthy(g) for g in GATES}
    health["rights"] = healthy("rights", age=25 * 60)
    v = decide({g: ok(g) for g in GATES}, health)
    assert v.status == "BLOCK" and v.motive == "control unavailable" and v.needs_human
    assert any("rights: control unavailable" in r for r in v.reasons)


def test_errors_in_window_are_control_unavailable():
    health = {g: healthy(g) for g in GATES}
    health["brand"] = healthy("brand", err=0.5)
    v = decide({g: ok(g) for g in GATES}, health)
    assert v.motive == "control unavailable"


def test_missing_success_sample_is_unavailable():
    health = {g: healthy(g) for g in GATES}
    health["provenance"] = GateHealth("provenance", 0.0, None, 2.0)
    assert decide({g: ok(g) for g in GATES}, health).motive == "control unavailable"


def test_uncalibrated_pass_cannot_pass():
    health = {g: healthy(g) for g in GATES}
    health["claim"] = healthy("claim", catches=0)
    v = decide({g: ok(g) for g in GATES}, health)
    assert v.status == "BLOCK" and v.motive == "uncalibrated control" and v.needs_human
    assert "airlock:verdict:R2-uncalibrated" in v.rule_ids


def test_uncalibrated_block_still_blocks_on_content():
    results = {g: ok(g) for g in GATES}
    results["claim"] = ok("claim", status="BLOCK", reasons=["x"])
    health = {g: healthy(g) for g in GATES}
    health["claim"] = healthy("claim", catches=0)
    v = decide(results, health)
    assert v.status == "BLOCK" and v.motive == "content"


def test_instrument_error_needs_human():
    results = {g: ok(g) for g in GATES}
    results["rights"] = ok("rights", status="ERROR", reasons=["RuntimeError: boom"])
    v = decide(results, {g: healthy(g) for g in GATES})
    assert v.motive == "instrument error" and v.needs_human


def test_promql_names_the_gate():
    q = promql_questions("rights")
    assert 'gate="rights"' in q["error_rate_15m"] and "[15m]" in q["error_rate_15m"]
    assert "airlock_calibration_catches_total" in q["calibration_catches_7d"]
