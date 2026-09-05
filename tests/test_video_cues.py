"""The video script names a cue per beat and the recorder writes cues by name; the two must agree.

docs/VIDEO-SCRIPT.md places every voice line on a "(cue xxx)" the picture description names, and
video/record.mjs declares in CUE_NAMES every cue it can write (its cue() refuses any other). A beat
placed on a cue the recorder never writes would fall back to the script's timecode and land the
line on the wrong picture, so it fails here and in narrate.py before anything is synthesised.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NARRATE = ROOT / "video" / "narrate.py"


def load_narrate():
    spec = importlib.util.spec_from_file_location("narrate", NARRATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_script_cue_is_one_the_recorder_writes():
    narrate = load_narrate()
    beats = narrate.parse_script(narrate.SCRIPT)
    named = {beat["cue"] for beat in beats if beat["cue"]}
    assert named, "the script names no cue at all"
    assert narrate.check_cues(beats) == []
    assert named <= narrate.recorder_cues()


def test_every_beat_with_a_voice_names_a_cue():
    narrate = load_narrate()
    beats = narrate.parse_script(narrate.SCRIPT)
    unplaced = [beat["timecode_s"] for beat in beats if beat["voice"] and not beat["cue"]]
    assert unplaced == [], f"voice lines with no cue, they would land on the script timecode: {unplaced}"


def test_a_cue_the_recorder_does_not_know_is_reported(tmp_path):
    narrate = load_narrate()
    script = tmp_path / "script.md"
    script.write_text(
        '## 1. A section\n\n[0:00] The console (cue stake). | "One."\n'
        '[0:05] A beat on a cue nobody writes (cue nowhere). | "Two."\n',
        encoding="utf-8",
    )
    problems = narrate.check_cues(narrate.parse_script(script))
    assert any("nowhere" in problem for problem in problems)
    assert not any("stake" in problem for problem in problems)
