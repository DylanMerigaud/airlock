"""The console reads the verdict's PromQL from console/src/lib/promql.json; that file must be the export.

A drift between airlock.verdict.promql_questions and the committed JSON fails here, so the console
can never model fewer (or different) questions than the verdict asks. Fix: uv run python scripts/export_promql.py
"""

import importlib.util
import json
from pathlib import Path

from airlock.gates.base import GATES
from airlock.verdict import promql_questions

ROOT = Path(__file__).resolve().parents[1]
EXPORTER = ROOT / "scripts" / "export_promql.py"
COMMITTED = ROOT / "console" / "src" / "lib" / "promql.json"


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_promql", EXPORTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_json_equals_a_fresh_export():
    exporter = load_exporter()
    assert COMMITTED.exists(), "run: uv run python scripts/export_promql.py"
    assert json.loads(COMMITTED.read_text()) == exporter.build()
    assert COMMITTED.read_text() == exporter.render(exporter.build()), "formatting differs: re-run the exporter"


def test_export_carries_every_question_the_verdict_asks_for_every_gate():
    payload = load_exporter().build()
    assert list(payload["gates"]) == list(GATES)
    for gate in GATES:
        asked = promql_questions(gate)
        for key, expr in asked.items():
            assert payload["gates"][gate][key] == expr, f"{gate}.{key} differs from promql_questions"
        assert set(payload["keys"]) >= set(asked)


def test_export_always_carries_seconds_since_success_for_the_console():
    payload = load_exporter().build()
    for gate in GATES:
        expr = payload["gates"][gate]["seconds_since_success"]
        assert "airlock_gate_last_success_ts" in expr and f'gate="{gate}"' in expr


def test_check_mode_exits_zero_on_the_committed_file(capsys):
    exporter = load_exporter()
    assert exporter.main(["--check"]) == 0
    assert "matches" in capsys.readouterr().out


def test_check_mode_exits_one_on_a_stale_file(tmp_path, capsys):
    exporter = load_exporter()
    stale = tmp_path / "promql.json"
    stale.write_text("{}\n")
    assert exporter.main(["--check", "--output", str(stale)]) == 1
    assert "stale" in capsys.readouterr().err
