import re

from airlock.calibrate import DEFECTS, ledger_lines
from airlock.gates.base import GATES
from airlock.verdict import promql_questions


def test_every_gate_has_at_least_one_defect():
    assert {d.gate for d in DEFECTS} == set(GATES)


def test_provenance_has_both_defect_shapes():
    names = [d.name for d in DEFECTS if d.gate == "provenance"]
    assert any("stripped" in n for n in names) and any("flipped" in n for n in names)


def test_ledger_lines_carry_one_series_per_defect():
    """airlock_calibration{gate, defect}: a gate with two defects pushes two series, so the verdict's
    `min by ()` over the gate's last samples reads a miss on either one (before 2026-09-05 the two
    provenance lines shared one series and the last push won)."""
    rows = [{"gate": "provenance", "slug": "manifest-stripped", "caught": False},
            {"gate": "provenance", "slug": "byte-flipped", "caught": True},
            {"gate": "claim", "slug": "unsubstantiated-endorsement", "caught": True}]
    lines = ledger_lines(rows)
    assert lines[0].startswith("airlock_calibration,defect=manifest-stripped,gate=provenance catches_total=0i,misses_total=1i,runs_total=1i ")
    assert lines[1].startswith("airlock_calibration,defect=byte-flipped,gate=provenance catches_total=1i,misses_total=0i,runs_total=1i ")
    assert lines[2].startswith("airlock_calibration,defect=unsubstantiated-endorsement,gate=claim catches_total=1i")
    assert len({ln.split(" ")[0] for ln in lines}) == 3  # three distinct series
    assert promql_questions("provenance")["last_calibration_caught"].startswith("min by () (last_over_time(airlock_calibration_catches_total")


def test_every_defect_slug_is_unique_and_label_safe():
    slugs = [d.slug for d in DEFECTS]
    assert len(set(slugs)) == len(slugs)
    assert all(re.fullmatch(r"[a-z0-9-]+", s) for s in slugs)
