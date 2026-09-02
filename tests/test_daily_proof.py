import json
import os

from airlock.calibrate import DEFECTS, Defect
from airlock.daily_proof import ensure_inputs, proof_line, summarize
from airlock.engine_client import parse_sse_line


def _rows(caught: bool = True, miss_gate: str | None = None) -> list[dict]:
    rows = []
    for d in DEFECTS:
        ok = caught and d.gate != miss_gate
        rows.append({"gate": d.gate, "defect": d.name, "expected": "BLOCK", "got": "BLOCK" if ok else "PASS",
                     "rule_ids": [d.expected_rule_substring] if ok else ["16 CFR 255.1"], "caught": ok, "elapsed_ms": 10,
                     "cost_usd": {"rights": 0.5, "claim": 0.004, "brand": 0.001}.get(d.gate, 0.0)})
    return rows


VERDICT_PASS = {"stage": "verdict", "status": "PASS", "motive": "content", "needs_human": False, "annotation_id": 51,
                "reasons": ["all 4 gates PASS, healthy and calibrated"], "cost": {"cost_usd": 0.5053, "per_gate": {"rights": 0.5}}}
VERDICT_BLOCK = {"stage": "verdict", "status": "BLOCK", "motive": "uncalibrated control", "needs_human": True, "annotation_id": 52,
                 "reasons": ["claim: PASS is advisory only, last calibration run MISSED its defect"], "cost": {"cost_usd": 0.5}}


def test_all_caught_and_pass_is_a_pass_with_exit_0():
    s = summarize(_rows(), VERDICT_PASS, {"inputs": 0.04, "calibration": 61.26, "clean_clip": 48.0})
    assert s.outcome == "pass" and s.exit_code == 0 and s.reasons == []
    assert s.gates == {"rights": "CAUGHT", "claim": "CAUGHT", "brand": "CAUGHT", "provenance": "CAUGHT"}
    assert s.annotation_id == 51 and s.verdict == "PASS"
    assert s.clean_clip_cost_usd == 0.5053 and s.calibration_cost_usd == 0.505 and s.cost_usd == 1.0103
    assert s.elapsed_s == {"inputs": 0.0, "calibration": 61.3, "clean_clip": 48.0}
    assert json.loads(json.dumps(s.to_dict()))["outcome"] == "pass"


def test_one_missed_defect_fails_and_names_the_gate():
    s = summarize(_rows(miss_gate="claim"), VERDICT_PASS, {})
    assert s.outcome == "fail" and s.exit_code == 1
    assert s.gates["claim"] == "MISSED" and s.gates["rights"] == "CAUGHT"
    assert any(r.startswith("claim: MISSED expert endorsement") for r in s.reasons)


def test_provenance_needs_both_defects_caught():
    rows = _rows()
    broken = next(r for r in rows if "flipped" in r["defect"])
    broken["caught"] = False
    s = summarize(rows, VERDICT_PASS, {})
    assert s.gates["provenance"] == "MISSED" and s.outcome == "fail"


def test_block_verdict_fails_with_the_motive():
    s = summarize(_rows(), VERDICT_BLOCK, {})
    assert s.outcome == "fail" and s.verdict == "BLOCK" and s.motive == "uncalibrated control" and s.annotation_id == 52
    assert s.reasons == ["verdict BLOCK (uncalibrated control): claim: PASS is advisory only, last calibration run MISSED its defect"]


def test_no_verdict_event_fails():
    s = summarize(_rows(), None, {})
    assert s.outcome == "fail" and s.verdict is None and s.clean_clip_cost_usd is None and s.cost_usd == 0.505
    assert "no verdict event from Agent Engine" in s.reasons


def test_cost_is_none_only_when_nothing_could_be_priced():
    rows = [dict(r, cost_usd=None) for r in _rows()]
    s = summarize(rows, None, {})
    assert s.cost_usd is None and s.calibration_cost_usd is None


def test_a_gate_with_no_row_fails():
    rows = [r for r in _rows() if r["gate"] != "brand"]
    s = summarize(rows, VERDICT_PASS, {})
    assert s.gates["brand"] == "MISSED" and "brand: no calibration row" in s.reasons


def test_a_failure_on_the_way_fails_even_when_everything_else_passed():
    s = summarize(_rows(), VERDICT_PASS, {}, failures=["calibration ledger not pushed: RuntimeError: influx push failed: HTTP 503"])
    assert s.outcome == "fail" and s.reasons[0].startswith("calibration ledger not pushed")


def test_proof_line_is_the_series_the_dashboard_reads():
    assert proof_line("pass", ts_ns=1700000000000000000) == "airlock_daily_proof,outcome=pass total=1i 1700000000000000000"
    assert proof_line("fail", ts_ns=1).startswith("airlock_daily_proof,outcome=fail total=1i")
    assert proof_line("pass", ts_ns=1, cost_usd=1.011551) == "airlock_daily_proof,outcome=pass cost_usd=1.011551,total=1i 1"


def test_ensure_inputs_downloads_only_what_is_missing(tmp_path):
    present = tmp_path / "assets" / "real" / "present.mp4"
    present.parent.mkdir(parents=True)
    present.write_bytes(b"x")
    defects = [Defect("rights", "present", str(present), "gs://b/real/present.mp4", "BLOCK", "x"),
               Defect("claim", "missing", str(tmp_path / "assets" / "synthetic" / "missing.mp4"), "gs://b/synthetic/missing.mp4", "BLOCK", "x")]
    clean = {"claim": (str(tmp_path / "assets" / "synthetic" / "calibration" / "clean.mp4"), "gs://b/calibration/clean.mp4")}
    calls = []

    def fake_download(gcs_uri: str, dest_dir: str) -> str:
        calls.append(gcs_uri)
        dest = os.path.join(dest_dir, gcs_uri.rsplit("/", 1)[1])
        with open(dest, "wb") as f:
            f.write(b"y")
        return dest

    fetched = ensure_inputs(defects, clean, download=fake_download)
    assert sorted(calls) == ["gs://b/calibration/clean.mp4", "gs://b/synthetic/missing.mp4"]
    assert sorted(fetched) == sorted([defects[1].local_path, clean["claim"][0]])
    assert os.path.exists(defects[1].local_path) and os.path.exists(clean["claim"][0])
    assert ensure_inputs(defects, clean, download=fake_download) == []  # the second call fetches nothing


def test_parse_sse_line_reads_the_verdict_payload():
    ev = parse_sse_line('data: {"author": "verdict", "content": {"parts": [{"text": "' + json.dumps(VERDICT_PASS).replace('"', '\\"') + '"}]}}', 45.6)
    assert ev is not None and ev.author == "verdict" and ev.t == 45.6 and ev.error is None
    assert ev.payloads()[0]["annotation_id"] == 51
    assert parse_sse_line("", 1.0) is None
    assert parse_sse_line(": keepalive", 1.0).unparsed == ": keepalive"
    err = parse_sse_line('{"author": "rights_gate", "error_message": "boom"}', 2.0)
    assert err.error == "boom" and err.texts == [] and err.payloads() == []
