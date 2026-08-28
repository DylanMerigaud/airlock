from airlock.calibrate import DEFECTS
from airlock.gates.base import GATES


def test_every_gate_has_at_least_one_defect():
    assert {d.gate for d in DEFECTS} == set(GATES)


def test_provenance_has_both_defect_shapes():
    names = [d.name for d in DEFECTS if d.gate == "provenance"]
    assert any("stripped" in n for n in names) and any("flipped" in n for n in names)
