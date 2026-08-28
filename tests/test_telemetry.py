from airlock.telemetry import line


def test_line_formats_tags_and_int_fields():
    out = line("airlock_gate", {"gate": "rights"}, {"runs_total": 1, "elapsed_ms": 240}, ts_ns=1700000000000000000)
    assert out == "airlock_gate,gate=rights elapsed_ms=240i,runs_total=1i 1700000000000000000"


def test_line_escapes_tag_values():
    out = line("m", {"gate": "a b,c=d"}, {"v": 1.5}, ts_ns=1)
    assert out == "m,gate=a\\ b\\,c\\=d v=1.5 1"


def test_line_rejects_empty_fields():
    import pytest

    with pytest.raises(ValueError):
        line("m", {}, {}, ts_ns=1)
