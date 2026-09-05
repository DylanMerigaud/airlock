#!/usr/bin/env python3
"""narrate.py: turn the voice lines of docs/VIDEO-SCRIPT.md into a synthetic narration track.

Every line of the shooting script has the shape

    [m:ss] what is on screen | "what the voice says"

This reads those lines, places each one where the picture actually is (the cue times the recorder
wrote into video/out/cues.json, the script timecode as the fallback), synthesises it with Google
Cloud Text to Speech, and writes video/out/narration.json for assemble.py.

The voice here is synthetic and the draft says so in its file name. The final voice is Dylan's,
recorded separately from the same script.

    uv run --group video python video/narrate.py
    uv run --group video python video/narrate.py --voice en-US-Neural2-D --out video/out
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "docs" / "VIDEO-SCRIPT.md"

PREFERRED_VOICE = "en-US-Neural2-D"
FALLBACK_VOICE = "en-US-Neural2-D"
LANGUAGE = "en-US"
SAMPLE_RATE = 24_000
# The read is at 1.1: the script is cut for pace and a line has to be over before the picture it
# describes is, so the words come faster rather than the beats getting longer.
SPEAKING_RATE = 1.1
MIN_GAP_S = 0.4
# Text to Speech hands back a fifth of a second of silence at each end of every line. Eighteen
# lines of that is four seconds of nothing, and worse, it is four seconds that push the next line
# off the picture it belongs to, because a line never starts before the one before it has ended.
# So each wav is trimmed to its speech and given back a short tail, and the trim is written down.
SILENCE_FLOOR_DB = -50
TAIL_S = 0.08

# Which cue of the take each beat is spoken over is named by the script itself: every picture
# description carries "(cue xxx)", and a beat that names two cues is placed on the first. A beat
# that names none keeps the script's timecode, which is what the opening overlay and the quotes
# need. Nothing here is positional any more, so a beat can be added to the script without
# renumbering anything in this file.
CUE_IN_PICTURE = re.compile(r"\(cue\s+([a-z0-9_]+)")

BEAT = re.compile(r"^\[(\d+):(\d{2})\]\s*(.*)$")


def parse_script(path: Path) -> list[dict]:
    """Return one entry per beat: section, index, timecode, picture, voice (None when silent)."""
    beats: list[dict] = []
    section: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        heading = re.match(r"^##\s+(\d)\.", line)
        if heading:
            section = heading.group(1)
            continue
        if line.startswith("## "):
            section = None
            continue
        if section is None:
            continue
        match = BEAT.match(line)
        if not match:
            continue
        minutes, seconds, rest = match.groups()
        timecode = int(minutes) * 60 + int(seconds)
        picture, _, spoken = rest.rpartition(" | ")
        spoken = spoken.strip()
        silent = spoken.startswith("(") or not picture
        voice = None if silent else spoken.strip('"').strip()
        named = CUE_IN_PICTURE.search(picture)
        beats.append(
            {
                "section": section,
                "index": sum(1 for b in beats if b["section"] == section),
                "timecode_s": float(timecode),
                "picture": picture.strip(),
                "voice": voice,
                "cue": named.group(1) if named else None,
            }
        )
    return beats


def trim_silence(path: Path) -> float:
    """Cut the silence off both ends of a synthesised line, leaving a short tail.

    Returns how many seconds came off. The file is replaced in place, so narration.json and the
    mix downstream read the trimmed length and nothing has to know this happened.
    """
    before = wav_duration(path)
    trimmed = path.with_suffix(".trimmed.wav")
    edge = (
        f"silenceremove=start_periods=1:start_duration=0:start_threshold={SILENCE_FLOOR_DB}dB"
        ":detection=peak"
    )
    result = subprocess.run(
        ["ffmpeg", "-y", "-nostdin", "-v", "error", "-i", str(path), "-af",
         f"{edge},areverse,{edge},areverse,apad=pad_dur={TAIL_S}", str(trimmed)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not trimmed.exists():
        print(f"  could not trim {path.name}, keeping it whole: {result.stderr.strip()[:200]}")
        trimmed.unlink(missing_ok=True)
        return 0.0
    trimmed.replace(path)
    return round(before - wav_duration(path), 3)


def wav_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip())


def pick_voice(client, wanted: str) -> str:
    names = {v.name for v in client.list_voices(request={"language_code": LANGUAGE}).voices}
    if wanted in names:
        return wanted
    if FALLBACK_VOICE in names:
        print(f"voice {wanted} is not offered on this project, falling back to {FALLBACK_VOICE}")
        return FALLBACK_VOICE
    raise SystemExit(f"neither {wanted} nor {FALLBACK_VOICE} is available; got {sorted(names)[:5]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "video" / "out"), help="output directory")
    ap.add_argument("--voice", default=PREFERRED_VOICE)
    ap.add_argument("--script", default=str(SCRIPT))
    args = ap.parse_args()

    out = Path(args.out)
    voice_dir = out / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)

    beats = parse_script(Path(args.script))
    cues_path = out / "cues.json"
    cue_times: dict[str, float] = {}
    take = {}
    if cues_path.exists():
        take = json.loads(cues_path.read_text(encoding="utf-8"))
        for entry in take.get("cues", []):
            cue_times.setdefault(entry["cue"], float(entry["t"]))
    else:
        print(f"no {cues_path}: every line falls back to the script timecode")

    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()
    voice_name = pick_voice(client, args.voice)
    voice = texttospeech.VoiceSelectionParams(language_code=LANGUAGE, name=voice_name)
    audio = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        sample_rate_hertz=SAMPLE_RATE,
        speaking_rate=SPEAKING_RATE,
    )

    lines: list[dict] = []
    missing: list[str] = []
    for beat in beats:
        # The script names the cue; a beat that names none, or one the take never reached, keeps
        # the script's own timecode and says so in narration.json under start_source.
        named = beat["cue"]
        if beat["voice"] is None:
            print(f"silent beat at {beat['timecode_s']:.0f}s ({named or 'no cue'}), nothing to synthesise")
            continue
        if named and named not in cue_times:
            missing.append(named)
        source = "cue" if named in cue_times else "timecode"
        start = cue_times[named] if source == "cue" else beat["timecode_s"]
        cue = named or f"t{int(beat['timecode_s'])}"
        lines.append(
            {
                "cue": cue,
                "text": beat["voice"],
                "timecode_s": beat["timecode_s"],
                "cue_t": start,
                "start_source": source,
                "start_s": start,
            }
        )

    lines.sort(key=lambda entry: entry["start_s"])
    for position, line in enumerate(lines):
        name = f"{position + 1:02d}-{line['cue']}.wav"
        path = voice_dir / name
        response = client.synthesize_speech(
            request={
                "input": texttospeech.SynthesisInput(text=line["text"]),
                "voice": voice,
                "audio_config": audio,
            }
        )
        path.write_bytes(response.audio_content)
        line["wav"] = str(path.relative_to(out))
        line["trimmed_s"] = trim_silence(path)
        line["duration_s"] = round(wav_duration(path), 3)
        print(f"{name}: {line['duration_s']:6.2f}s (-{line['trimmed_s']:.2f}s silence)"
              f"  at {line['start_s']:7.2f}s ({line['start_source']})")

    # A line never lands on top of the one before it: it slides to the previous end plus a beat,
    # and the shift is recorded so the take can be re-cut if a beat is systematically too tight.
    previous_end = 0.0
    for line in lines:
        wanted = line["start_s"]
        floor = previous_end + MIN_GAP_S if previous_end else 0.0
        line["shift_s"] = round(max(0.0, floor - wanted), 3)
        line["start_s"] = round(max(wanted, floor), 3)
        previous_end = line["start_s"] + line["duration_s"]

    payload = {
        "voice": voice_name,
        "synthetic": True,
        "language": LANGUAGE,
        "sample_rate_hz": SAMPLE_RATE,
        "speaking_rate": SPEAKING_RATE,
        "min_gap_s": MIN_GAP_S,
        "silence_trimmed_s": round(sum(line["trimmed_s"] for line in lines), 3),
        "take": {
            "recorded_at": take.get("recorded_at"),
            "duration_s": take.get("duration_s"),
        },
        "narration_end_s": round(previous_end, 3),
        "lines": lines,
    }
    (out / "narration.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    shifted = [line for line in lines if line["shift_s"] > 0]
    print()
    for name in missing:
        print(f"  the take has no cue {name}, that line fell back to the script timecode")
    spoken = sum(line["duration_s"] for line in lines)
    trimmed = sum(line["trimmed_s"] for line in lines)
    print(f"{len(lines)} lines, voice {voice_name} at {SPEAKING_RATE}x, {spoken:.1f}s spoken, "
          f"{trimmed:.1f}s of silence trimmed, narration ends at {previous_end:.1f}s")
    for line in shifted:
        print(f"  shifted {line['cue']} by {line['shift_s']:.2f}s to avoid an overlap")
    worst = max((line["shift_s"] for line in lines), default=0.0)
    print(f"  the largest shift on the take's own cue times is {worst:.2f}s")
    print(f"wrote {out / 'narration.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
