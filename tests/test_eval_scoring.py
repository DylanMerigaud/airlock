"""The eval's scoring, on a small fixture: per gate, per rule, brand naming, the manifest loader.
No gate runs here and nothing reaches the cloud."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("eval_gates", ROOT / "scripts" / "eval_gates.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["eval_gates"] = mod  # a dataclass under postponed annotations needs its module registered
    spec.loader.exec_module(mod)
    return mod


eg = _load()


def _asset(asset_id: str, kind: str, gates: dict, ground_truth: dict) -> dict:
    return {"asset_id": asset_id, "kind": kind, "gates": gates, "ground_truth": ground_truth}


# Two real spots and one synthetic clip, shaped like results.json rows.
KODAK = _asset("kodak", "real", {
    "rights": {"status": "BLOCK", "reason": "explicit content likelihood at or above LIKELY on 2 frame(s)",
               "rule_ids": ["registry:brands:unknown", "registry:explicit_content", "registry:faces:no_release"],
               "found": {"brands": [{"name": "Kodak", "how": "logo"}]}},
    "provenance": {"status": "BLOCK", "reason": "no C2PA manifest", "rule_ids": ["airlock:provenance:manifest-required"]},
}, {"status": {"rights": "BLOCK", "provenance": "BLOCK"},
    "rules_expected": {"rights": ["registry:brands:unknown", "registry:faces:no_release"], "provenance": ["airlock:provenance:manifest-required"]},
    "rules_forbidden": {"rights": ["registry:explicit_content"]},
    "brand_names": ["Kodak", "Instamatic"]})

CHEVROLET = _asset("chevrolet", "real", {
    "rights": {"status": "BLOCK", "reason": "a logo the registry does not know", "rule_ids": ["registry:brands:unknown"],
               "found": {"brands": [{"name": "DeLorean Motor Company", "how": "logo"}]}},
    "provenance": {"status": "PASS", "reason": "verified", "rule_ids": ["airlock:provenance:manifest-required", "airlock:provenance:signature-valid"]},
}, {"status": {"rights": "BLOCK", "provenance": "BLOCK"},
    "rules_expected": {"rights": ["registry:brands:unknown"], "provenance": ["airlock:provenance:manifest-required"]},
    "rules_forbidden": {"rights": ["registry:explicit_content", "registry:faces:no_release"]},
    "brand_names": ["Chevrolet", "Chevy"]})

CLEAN = _asset("clean", "synthetic", {
    "rights": {"status": "PASS", "reason": "no brand", "rule_ids": ["registry:brands", "registry:faces", "registry:explicit_content"]},
    "claim": {"status": "PASS", "reason": "nothing regulated", "rule_ids": ["16 CFR 255.1"]},
}, {"status": {"rights": "PASS", "claim": "PASS"},
    "rules_expected": {},
    "rules_forbidden": {"rights": ["registry:explicit_content"], "claim": ["16 CFR 255.3"]},
    "brand_names": []})

FIXTURE = [KODAK, CHEVROLET, CLEAN]


def test_a_pass_never_fires_the_rules_it_lists():
    assert eg.fired(CLEAN["gates"]["rights"]) == set()
    assert eg.fired(KODAK["gates"]["rights"]) == {"registry:brands:unknown", "registry:explicit_content", "registry:faces:no_release"}
    assert eg.fired(None) == set()


def test_status_score_counts_a_pass_where_block_was_expected_as_a_miss():
    s = eg.score_status(FIXTURE)
    assert s["rights"] == {"tp": 2, "fp": 0, "tn": 1, "fn": 0, "n": 3, "precision": 1.0, "recall": 1.0, "misses": []}
    assert s["provenance"]["tp"] == 1 and s["provenance"]["fn"] == 1 and s["provenance"]["n"] == 2
    assert s["provenance"]["recall"] == 0.5
    assert s["provenance"]["misses"] == [("chevrolet", "BLOCK", "PASS")]
    assert s["brand"]["n"] == 0 and s["brand"]["precision"] is None


def test_rule_score_counts_a_forbidden_rule_that_fires_as_a_false_positive():
    r = eg.score_rules(FIXTURE)
    explicit = r["registry:explicit_content"]
    # forbidden on all three; fired on Kodak only
    assert (explicit["tp"], explicit["fp"], explicit["tn"], explicit["fn"], explicit["n"]) == (0, 1, 2, 0, 3)
    assert explicit["precision"] == 0.0
    assert explicit["false_positives"] == [("kodak", "explicit content likelihood at or above LIKELY on 2 frame(s)")]
    unknown = r["registry:brands:unknown"]
    assert (unknown["tp"], unknown["fn"], unknown["n"]) == (2, 0, 2) and unknown["recall"] == 1.0
    faces = r["registry:faces:no_release"]
    assert (faces["tp"], faces["fp"], faces["tn"], faces["fn"]) == (1, 0, 1, 0)


def test_rule_score_treats_a_gate_that_did_not_block_as_silent():
    r = eg.score_rules(FIXTURE)
    manifest = r["airlock:provenance:manifest-required"]
    # Chevrolet's provenance PASSed while listing the rule: that is a miss, not a catch
    assert (manifest["tp"], manifest["fn"]) == (1, 1)
    assert manifest["misses"] == [("chevrolet", "PASS")]
    # a rule forbidden on a gate that never ran (claim on Kodak) is not counted at all
    assert r["16 CFR 255.3"]["n"] == 1 and r["16 CFR 255.3"]["tn"] == 1


def test_brand_named_matches_every_token_of_one_accepted_name():
    assert eg.brand_named(["General Electric", "GE"], ["General Electric Company"])
    assert eg.brand_named(["General Electric", "GE"], ["GE"])
    assert eg.brand_named(["Chevrolet", "Chevy"], ["chevy dealer"])
    assert not eg.brand_named(["Chevrolet", "Chevy"], ["DeLorean Motor Company"])
    assert not eg.brand_named(["Kodak"], [])


def test_brand_score_is_separate_from_the_block():
    s = eg.score_brand_names(FIXTURE)
    assert s["n"] == 2 and s["named"] == 1 and s["ratio"] == 0.5
    assert [r["asset_id"] for r in s["rows"] if not r["named"]] == ["chevrolet"]


def test_surprises_name_the_false_positive_the_miss_and_the_misnamed_brand():
    text = "\n".join(eg.surprises(FIXTURE))
    assert "`registry:explicit_content` fired on `kodak`" in text
    assert "`airlock:provenance:manifest-required` did not fire on `chevrolet`" in text
    assert "did not name the brand on 1 of 2 real spots" in text
    assert "DeLorean Motor Company" in text


def test_every_percentage_carries_its_count():
    assert eg.fmt_pct(1.0, 10, 10) == "100% (10 of 10)"
    assert eg.fmt_pct(0.5, 1, 2) == "50% (1 of 2)"
    assert eg.fmt_pct(None) == "n/a (0 of 0)"


def test_manifest_loads_sixteen_assets_and_the_faces_label_places_the_release_rule():
    specs = eg.load_manifest(bucket="b")
    assert len(specs) == 16
    by_id = {s.asset_id: s for s in specs}
    cheerios = by_id["Cheerios1960-0-30"]
    assert cheerios.faces is True
    assert "registry:faces:no_release" in cheerios.rules_expected["rights"]
    assert "registry:brands:unknown" in cheerios.rules_expected["rights"]
    assert cheerios.status == {"rights": "BLOCK", "provenance": "BLOCK"}
    assert cheerios.gcs_uri == "gs://b/real/eval/Cheerios1960-0-30.mp4"
    scotties = by_id["ScottiesTiss-0-30"]
    assert scotties.faces is False
    assert "registry:faces:no_release" in scotties.rules_forbidden["rights"]
    assert "registry:faces:no_release" not in scotties.rules_expected["rights"]
    veo = by_id["veo-raw"]
    assert veo.gcs_uri is None and veo.kind == "synthetic"
    assert veo.rules_expected["provenance"] == ["airlock:provenance:signer-trusted"]


def test_every_rule_id_in_the_manifest_is_one_a_gate_emits():
    specs = eg.load_manifest()
    unknown = eg.manifest_rule_ids(specs) - eg.known_rule_ids()
    assert unknown == set(), f"rule ids in eval/manifest.yaml that no gate emits: {sorted(unknown)}"


def test_known_rule_ids_cover_the_four_gates():
    ids = eg.known_rule_ids()
    for rule in ("registry:brands:unknown", "registry:faces:no_release", "registry:explicit_content",
                 "charter:mandatory_mentions", "charter:palette", "airlock:provenance:signer-trusted", "16 CFR 255.3"):
        assert rule in ids


def test_eval_md_prints_n_beside_every_percentage(tmp_path, monkeypatch):
    monkeypatch.setattr(eg, "EVAL_MD_PATH", tmp_path / "EVAL.md")
    payload = {"started": "s", "finished": "f", "bucket": "b", "code": "abc1234", "manifest": "eval/manifest.yaml", "assets": FIXTURE}
    eg.write_eval_md(payload)
    text = (tmp_path / "EVAL.md").read_text()
    assert "| rights | 3 | 2 | 0 | 1 | 0 | 100% (2 of 2) | 100% (2 of 2) |" in text
    assert "| `registry:explicit_content` | rights | 3 | 0 | 1 | 2 | 0 | 0% (0 of 1) | n/a (0 of 0) |" in text
    assert "Brand named: 50% (1 of 2)." in text
    assert "## Surprises" in text and "kodak_instamatic-31-60" in text
    for m in re.finditer(r"\d+%", text):
        tail = text[m.end():m.end() + 2]
        assert tail == " (", f"a bare percentage at {m.start()}: {text[m.start() - 20:m.end() + 20]!r}"


def test_only_rerun_replaces_its_rows_and_keeps_the_rest_in_manifest_order():
    previous = [{"asset_id": "b", "gates": {"rights": {"status": "PASS"}}}, {"asset_id": "a", "gates": {}}, {"asset_id": "zzz", "gates": {}}]
    fresh = [{"asset_id": "b", "gates": {"rights": {"status": "BLOCK"}}}]
    merged = eg.merge_rows(previous, fresh, order=["a", "b"])
    assert [r["asset_id"] for r in merged] == ["a", "b", "zzz"]
    assert merged[1]["gates"]["rights"]["status"] == "BLOCK"


def test_run_eval_checkpoints_after_every_asset_and_marks_the_file_partial(tmp_path, monkeypatch):
    seen = []

    def fake_run_one(spec):
        seen.append(spec.asset_id)
        return {"asset_id": spec.asset_id, "kind": spec.kind, "gates": {}, "ground_truth": spec.ground_truth()}

    monkeypatch.setattr(eg, "run_one", fake_run_one)
    monkeypatch.setattr(eg, "code_version", lambda: "test")
    specs = [eg.AssetSpec("x", "synthetic", "no/file", None), eg.AssetSpec("y", "synthetic", "no/file", None)]
    checkpoint = tmp_path / "results.json"
    payload = eg.run_eval(specs, previous={"started": "earlier", "assets": [{"asset_id": "w", "gates": {}}]}, order=["w", "x", "y"], checkpoint=checkpoint)
    assert seen == ["x", "y"]
    assert payload["partial"] is False and payload["started"] == "earlier"
    assert [r["asset_id"] for r in payload["assets"]] == ["w", "x", "y"]
    on_disk = json.loads(checkpoint.read_text())
    assert on_disk == payload


def test_watchdog_turns_a_hang_into_a_timeout_error():
    import time
    with pytest.raises(TimeoutError, match="eval watchdog: slow exceeded 1 s"):
        with eg.asset_watchdog("slow", budget_s=1):
            time.sleep(3)
    # disarmed after the block: a later sleep is not interrupted
    with eg.asset_watchdog("fast", budget_s=1):
        pass
    time.sleep(1.2)
