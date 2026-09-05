from airlock.verdict import ERROR_RATIO_BLOCK, ERROR_RUNS_MIN, GateHealth, decide, logql_question, promql_questions

GATES = ["rights", "claim", "brand", "provenance"]


def ok(gate, **over):
    return {"gate": gate, "status": over.get("status", "PASS"), "reasons": over.get("reasons", ["fine"]), "rule_ids": over.get("rule_ids", [])}


def healthy(gate, **over):
    return GateHealth(gate, error_rate_15m=over.get("err", 0.0), seconds_since_success=over.get("age", 30.0),
                      calibration_catches_7d=over.get("catches", 3.0), last_calibration_caught=over.get("last", 1.0),
                      seen_this_run=over.get("seen", True), runs_15m=over.get("runs", 4.0))


def test_all_pass_seen_healthy_calibrated_is_pass():
    v = decide({g: ok(g) for g in GATES}, {g: healthy(g) for g in GATES})
    assert v.status == "PASS" and not v.needs_human
    assert "seen by Grafana" in v.reasons[0]


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


# R1: this run's event is the proof. A muted gate pushes nothing, so Loki never sees it, whatever the gate said.


def test_muted_gate_pass_not_seen_is_control_unavailable_and_needs_human():
    health = {g: healthy(g) for g in GATES}
    health["rights"] = healthy("rights", seen=False)
    v = decide({g: ok(g) for g in GATES}, health)
    assert v.status == "BLOCK" and v.motive == "control unavailable" and v.needs_human
    assert "rights: control unavailable (NOT seen by Grafana for this run)" in v.reasons
    assert "airlock:verdict:R1-control-unavailable" in v.rule_ids
    assert [row for row in v.gate_lines if row["gate"] == "rights"][0]["seen_this_run"] is False


def test_the_same_gate_seen_passes():
    health = {g: healthy(g) for g in GATES}
    health["rights"] = healthy("rights", seen=True)
    v = decide({g: ok(g) for g in GATES}, health)
    assert v.status == "PASS"


def test_loki_unreadable_fails_closed():
    health = {g: healthy(g) for g in GATES}
    health["brand"] = healthy("brand", seen=None)
    v = decide({g: ok(g) for g in GATES}, health)
    assert v.motive == "control unavailable"
    assert any("could not be read" in r for r in v.reasons)


def test_staleness_alone_no_longer_blocks():
    health = {g: healthy(g) for g in GATES}
    health["rights"] = healthy("rights", age=25 * 60)
    v = decide({g: ok(g) for g in GATES}, health)
    assert v.status == "PASS"
    assert "last success 1500 s ago" in health["rights"].describe()


def test_missing_success_sample_is_informational_when_the_run_is_seen():
    health = {g: healthy(g) for g in GATES}
    health["provenance"] = healthy("provenance", age=None)
    v = decide({g: ok(g) for g in GATES}, health)
    assert v.status == "PASS"
    assert "no success sample" in health["provenance"].describe()


def test_one_error_in_three_runs_does_not_block():
    health = {g: healthy(g) for g in GATES}
    health["brand"] = healthy("brand", err=1 / 3, runs=3.0)
    v = decide({g: ok(g) for g in GATES}, health)
    assert v.status == "PASS"
    assert "under the 50% block line" in health["brand"].describe()


def test_a_majority_of_errors_over_two_runs_blocks():
    health = {g: healthy(g) for g in GATES}
    health["brand"] = healthy("brand", err=ERROR_RATIO_BLOCK, runs=float(ERROR_RUNS_MIN))
    v = decide({g: ok(g) for g in GATES}, health)
    assert v.motive == "control unavailable"
    assert any("error rate 50% over 15m (2 runs)" in r for r in v.reasons)


def test_all_errors_on_a_single_run_does_not_block():
    health = {g: healthy(g) for g in GATES}
    health["brand"] = healthy("brand", err=1.0, runs=1.0)
    assert decide({g: ok(g) for g in GATES}, health).status == "PASS"


def test_gate_error_is_control_unavailable_with_the_error_in_the_reason():
    results = {g: ok(g) for g in GATES}
    injected = "TimeoutError: Video Intelligence operation timed out after 1 s (fault injected for run e-1)"
    results["rights"] = ok("rights", status="ERROR", reasons=[injected])
    v = decide(results, {g: healthy(g) for g in GATES})
    assert v.status == "BLOCK" and v.motive == "control unavailable" and v.needs_human
    assert any(r.startswith("rights: control unavailable (instrument error: " + injected) for r in v.reasons)
    assert "airlock:verdict:R1-control-unavailable" in v.rule_ids and "airlock:verdict:instrument-error" in v.rule_ids


def test_gate_that_did_not_report_is_control_unavailable():
    results = {g: ok(g) for g in GATES if g != "claim"}
    v = decide(results, {g: healthy(g) for g in GATES})
    assert v.motive == "control unavailable" and any(r.startswith("claim: control unavailable") for r in v.reasons)


def test_content_block_with_a_dark_gate_needs_a_human():
    results = {g: ok(g) for g in GATES}
    results["provenance"] = ok("provenance", status="BLOCK", reasons=["broken"], rule_ids=["airlock:provenance:signature-valid"])
    health = {g: healthy(g) for g in GATES}
    health["rights"] = healthy("rights", seen=False)
    v = decide(results, health)
    assert v.status == "BLOCK" and v.motive == "content" and v.needs_human


# R2


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


def test_last_calibration_missed_makes_the_gate_advisory():
    health = {g: healthy(g) for g in GATES}
    health["claim"] = healthy("claim", catches=2.0, last=0.0)
    v = decide({g: ok(g) for g in GATES}, health)
    assert v.status == "BLOCK" and v.motive == "uncalibrated control"
    assert any("MISSED" in r for r in v.reasons)


# The questions


def test_promql_names_the_gate_and_has_five_questions():
    q = promql_questions("rights")
    assert set(q) == {"error_rate_15m", "runs_15m", "seconds_since_success", "calibration_catches_7d", "last_calibration_caught"}
    assert 'gate="rights"' in q["error_rate_15m"] and "[15m]" in q["error_rate_15m"]
    assert 'gate="rights"' in q["runs_15m"] and "airlock_gate_runs_total" in q["runs_15m"]
    assert "airlock_calibration_catches_total" in q["calibration_catches_7d"]


def test_promql_last_calibration_takes_the_min_over_the_defect_series():
    assert promql_questions("claim")["last_calibration_caught"].startswith("min by () (last_over_time(")


def test_logql_asks_for_this_run_of_this_gate():
    assert logql_question("rights", "e-abc123") == '{app="airlock", gate="rights"} |= "e-abc123"'


def test_new_claim_citations_are_paperwork_rules():
    # T6 moved the advertiser's own claims off Part 255: a study still lifts them, so they stay paperwork.
    from airlock.verdict import needs_paperwork

    assert needs_paperwork(["FTC Act section 5 (15 U.S.C. 45)"])
    assert needs_paperwork(["FTC Policy Statement Regarding Advertising Substantiation (1983)"])
    assert needs_paperwork(["CAP Code 3.7"])
    assert not needs_paperwork(["charter:exclusions"])
