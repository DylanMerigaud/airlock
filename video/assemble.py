#!/usr/bin/env python3
"""assemble.py: cut the take, lay the narration and the subtitles on it, and check the render.

Reads video/out/cues.json and video/out/narration.json, converts the Playwright webm to
1920x1080 at 30 fps constant, lays the Grafana pages the recorder opened on a second tab over the
console take for the windows they were open, burns the Article 50 overlay and the subtitles, mixes
the narration at its cue times over a room tone, and writes
video/out/airlock-draft-<n>-synthetic-voice.mp4 (or the name given with --output).

The take is longer than the video, because a real run takes as long as it takes. The only thing
the cut plan is allowed to remove is waiting, and every stretch of it says so on the picture before
it happens: "waiting for Video Intelligence, N s compressed" for the call the rights gate is
blocked on, "waiting for Grafana to draw, N s compressed" for the seconds a Grafana insert spends
building itself behind a settled verdict card. All of it comes off, down to the half second the
caption is spoken over; if that still leaves the render over the maximum, the dashboard hold and
then the landing hold are shortened and the assembler prints by how much. Nothing is ever padded to
reach a length. Every cue time is mapped through the cuts, so the narration stays on the picture it
describes, and the subtitles are cut one per sentence rather than one per spoken line.

The render check at the end is optional: AIRLOCK_RENDER_CHECK names a script run as
`python3 <script> --render <mp4> --limit-s 180` whose stdout says PASS or FAIL (the one used for the
drafts in docs/RUNS.md lives outside this repository). Unset, the step prints "render check skipped,
no checker configured" and the assembler exits 0 with the render written.

Every landing gets a punch-in: 1.15x over 1.2 s, eased in and out, towards the element that
changed, and the assembler then measures the thing the whole cut is for, the longest stretch of the
render with neither a change of picture nor a line playing.

    uv run python video/assemble.py
    uv run python video/assemble.py --draft 2 --max 175
    uv run python video/assemble.py --output airlock-v6-synthetic-voice.mp4
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RENDER_CHECK_ENV = "AIRLOCK_RENDER_CHECK"
FONT = os.environ.get("AIRLOCK_FONT", "/System/Library/Fonts/Supplemental/Arial Bold.ttf")


def render_checker() -> Path | None:
    """The render checker named by AIRLOCK_RENDER_CHECK, or None when none is configured or the path is missing."""
    raw = os.environ.get(RENDER_CHECK_ENV, "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.exists():
        print(f"render check skipped, {RENDER_CHECK_ENV}={raw} does not exist")
        return None
    return path

ARTICLE_50 = (
    "Article 50, EU AI Act, in force 2 August 2026: providers of AI systems generating "
    "synthetic content shall ensure the outputs are marked in a machine-readable format "
    "and detectable as artificially generated"
)
ARTICLE_50_S = 5.0
MIN_GAP_S = 0.3
GATE_ORDER = ("rights", "claim", "brand", "provenance")
TAIL_PAD_S = 1.2

# The punch-in. Every landing gets one: the frame pushes 1.15x towards the thing that changed over
# 1.2 s, eased in and eased out, and comes back. It is the only motion effect in the render; there
# are no transitions and no music.
#
# The centres are measured, not guessed: `node video/measure_layout.mjs` opens the live console at
# the take's own 1920x1080 and writes the bounding boxes to video/out/layout.json. Measured
# 2026-09-05 on the hosted console: verdict card (1484,59) 420x76, the seven check rows (1485,182)
# 418x509, the stage (16,59) 1456x862.
#
# At 1.15x the visible window is 1670x939 of the frame, so a centre can only travel 125 px
# horizontally and 70 px vertically before the crop would leave the picture. The centres below are
# therefore requests: build_punches clamps each one and writes both numbers into assembly.json.
# That is why the verdict punch and a gate punch land on the same effective point, one being the
# top of the right column and the other its middle, and both being further right than 1.15x can
# reach.
PUNCH_ZOOM = 1.15
PUNCH_S = 1.2
PUNCH_AT = {
    "checks": (1694, 436),   # the Checks column, where a gate row lands
    "verdict": (1694, 97),   # the verdict summary, top right
    "stage": (744, 490),     # the clip, left
}
ROOM_TONE_DBFS = -38.0  # above silencedetect's -45 dB floor, so a gap never reads as dead air

# A subtitle cue is one sentence, wrapped at about this width and never more than two rows, so a
# viewer reads a whole thought at once instead of a paragraph parked on the picture for 15 s.
SUBTITLE_WIDTH = 60
SUBTITLE_ROWS = 2
# Every stretch of waiting the assembler takes out is announced on the picture just before it
# happens, in a mono face so it reads as an editing note and not as console copy. Only waiting is
# ever cut this way, and the caption names what was being waited for: the Video Intelligence call
# the rights gate is blocked on, or the Grafana insert drawing its panels while the console take
# holds on the verdict card underneath.
#
# Script v5 cuts for pace, so two more kinds of waiting come out, both of them the same thing seen
# on another row: the seconds after the line about one gate has been said and before the next gate
# lands, and the seconds the verdict agent spends asking Grafana about each gate before the card
# fills. Script v6 adds the investigator: after the verdict card has filled and its line has been
# said, the language model agent is still reading Loki and the escalation has not landed yet.
# Nothing else changed: what is removed is still nothing but waiting, and it still says so on the
# picture, in the same words, in the same place.
WAIT_LABEL = {
    "run_wait": "waiting for Video Intelligence, {n} s compressed",
    "grafana_wait": "waiting for Grafana to draw, {n} s compressed",
    "gate_wait": "waiting for the {gate} gate, {n} s compressed",
    "verdict_wait": "waiting for the verdict agent, {n} s compressed",
    "investigation_wait": "waiting for the investigator, {n} s compressed",
}
# The voice is synthetic and the picture says so, top right, over the open and over the landing;
# the words come from narration.json so the caption cannot name a voice the mix does not carry.
VOICE_CAPTION_S = 8.0
VOICE_CAPTION_END_S = 6.0
VOICE_CAPTION_FONT_SIZE = 22
MONO_FONT = "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"
COMPRESSION_LABEL_S = 2.5
COMPRESSION_FONT_SIZE = 28
# How much of a wait survives its own cut. Half a second: enough that the viewer sees the picture
# the caption is talking about, short enough that no wait is ever a stretch of nothing.
WAIT_KEEP_S = 0.5
# A caption costs 2.5 s of the picture, so the smaller kinds only earn one when they take out this
# much or more (draft 5 asked for four seconds; script v6 carries 160 s of voice under a 180 s
# limit, and the render pays for every second of waiting kept). Under that the stretch stays in the
# render, where it is a couple of seconds of a clip playing under a row that reads "Checking", and
# it is counted in the pace measurement like everything else.
SMALL_WAIT_S = 2.5
# When compressing every wait leaves the render under the length it is meant to reach, whole waits
# go back on the picture, shortest first. Only short ones: a wait given back is a stretch of the
# render with nothing happening in it, and past this it costs the video more than the seconds are
# worth. A render that stays under the floor stays under it and says so.
GIVE_BACK_MAX_S = 6.0
# The recorder plays the claim seek right after the claim gate lands: it switches to the findings
# thread, clicks the time chip, holds the clip there and comes back (video/record.mjs, cues
# seek_claim and seek_done, SEEK_HOLD_MS). That beat sits inside the rights wait, and only waiting
# may be removed, so the window starts after it: what gets compressed has to be waiting and
# nothing else. seek_done says when the beat ended; this is the fallback for
# a take recorded before that cue existed.
SEEK_BEAT_S = 4.0


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def probe(path: Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)])
    return json.loads(out.stdout)


def duration_of(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def leading_black(path: Path, max_lead: float = 8.0) -> float:
    """How many seconds of the head of a clip are black.

    This is the fallback for the head of a Grafana insert. The measurement that decides it is the
    recorder's own `<name>_ready` cue, written into the overlay entry as `ready_at`: the instant
    the panels had drawn. Blackdetect only catches the blank tab, not the loading dashboard that
    follows it, so on its own it let ten seconds of a Grafana page building itself into draft 3.
    """
    out = run(["ffmpeg", "-nostdin", "-i", str(path), "-vf",
               "blackdetect=d=0.2:pic_th=0.98:pix_th=0.10", "-f", "null", "-"])
    ranges = sorted((float(a), float(b)) for a, b in
                    re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", out.stderr))
    lead = 0.0
    for start, end in ranges:
        if start > lead + 0.7 or end > max_lead:
            break
        lead = end
    return lead


def wrap(text: str, width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


# A sentence ends on a full stop, a question mark or an exclamation mark, and a colon starts a new
# one only when what follows is capitalised (so "not an opinion: this film" stays one cue).
SENTENCE_BREAK = re.compile(r"(?<=[.?!])\s+|(?<=:)\s+(?=[A-Z])")


def fit_chunks(text: str, width: int = SUBTITLE_WIDTH, rows: int = SUBTITLE_ROWS) -> list[str]:
    """Cut a sentence into the fewest pieces that each fit `rows` wrapped rows, evenly.

    A piece ends on a comma or a semicolon whenever one sits near the even split, because a cue
    that breaks between "and nobody" and "can prove" reads worse than an uneven one.
    """
    if len(wrap(text, width)) <= rows:
        return [text]
    words = text.split()
    for count in range(2, len(words) + 1):
        target = len(text) / count
        chunks, current = [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            over = len(candidate) > target and len(chunks) < count - 1
            if current and over:
                chunks.append(current)
                current = word
            else:
                current = candidate
        chunks.append(current)
        chunks = rebalance_on_punctuation(chunks, width, rows)
        if all(len(wrap(chunk, width)) <= rows for chunk in chunks):
            return chunks
    return [text]


def rebalance_on_punctuation(chunks: list[str], width: int, rows: int) -> list[str]:
    """Move the boundary between two pieces back to the last comma of the first one."""
    out = list(chunks)
    for i in range(len(out) - 1):
        left, right = out[i], out[i + 1]
        if left.endswith((",", ";", ":")):
            continue
        cut = max(left.rfind(", "), left.rfind("; "), left.rfind(": "))
        if cut <= 0:
            continue
        head, tail = left[: cut + 1], left[cut + 2 :]
        moved = f"{tail} {right}".strip()
        if len(wrap(head, width)) <= rows and len(wrap(moved, width)) <= rows:
            out[i], out[i + 1] = head, moved
    return out


def subtitle_cues(line: dict) -> list[dict]:
    """One cue per sentence of a spoken line, sharing that line's wav duration by length.

    The narration audio stays one wav per line; only the reading is split. The cues are
    contiguous and their lengths sum to exactly the wav duration, so nothing drifts.
    """
    pieces: list[str] = []
    for sentence in SENTENCE_BREAK.split(line["text"].strip()):
        sentence = sentence.strip()
        if sentence:
            pieces += fit_chunks(sentence)
    if not pieces:
        return []
    weights = [max(len(piece), 1) for piece in pieces]
    total_weight = sum(weights)
    begin, finish = line["start_final_s"], line["end_final_s"]
    span = finish - begin
    cues, carried, start = [], 0.0, begin
    for index, piece in enumerate(pieces):
        carried += weights[index]
        end = finish if index == len(pieces) - 1 else begin + span * carried / total_weight
        cues.append({"text": piece, "start": start, "end": end})
        start = end
    return cues


LANDING_CUE = re.compile(rf"^({'|'.join(GATE_ORDER)})_done(_\d+)?$")


def punch_target(cue: str) -> str | None:
    """Which element a cue's punch-in is centred on, or None for a cue that gets no punch.

    A landing only: a gate row settling, a verdict card filling, the clip jumping to the claim.
    `seek_done` is the camera coming back from that beat and gets nothing, or the punch would play
    twice on the same gesture.
    """
    if re.match(r"^verdict(_\d+)?$", cue):
        return "verdict"
    if cue == "seek_claim":
        return "stage"
    if cue == "resolved":
        # The incident reads resolved on the Record segment, in the right column.
        return "checks"
    if LANDING_CUE.match(cue):
        return "checks"
    return None


def build_punches(at_render: dict[str, float], total: float) -> tuple[list[dict], list[dict]]:
    """One punch-in per landing, in render time, with the collisions resolved.

    Two cues can land in the same second: the claim gate settles and the recorder clicks the time
    chip of its finding at once, so `claim_done` and `seek_claim` are 50 ms apart in the take. Two
    overlapping punches would sum into one 1.3x lurch, so they are resolved instead: when the later
    cue points at a different element, it wins, because that element is the one still on screen
    when the move plays. When it points at the same one, the earlier keeps it.
    """
    wanted = sorted(
        ({"cue": cue, "target": punch_target(cue), "t": at_render[cue]}
         for cue in at_render if punch_target(cue)),
        key=lambda entry: entry["t"],
    )
    kept: list[dict] = []
    dropped: list[dict] = []
    for entry in wanted:
        if entry["t"] > total - 0.2:
            dropped.append({**entry, "why": "after the end of the render"})
            continue
        if kept and entry["t"] < kept[-1]["t"] + PUNCH_S:
            previous = kept[-1]
            if entry["target"] == previous["target"]:
                dropped.append({**entry, "why": f"inside the {previous['cue']} punch, same centre"})
                continue
            kept[-1] = entry
            dropped.append({**previous, "why": f"{entry['cue']} lands on it, on another centre"})
            continue
        kept.append(entry)

    half_w, half_h = 1920 / (2 * PUNCH_ZOOM), 1080 / (2 * PUNCH_ZOOM)
    for entry in kept:
        cx, cy = PUNCH_AT[entry["target"]]
        entry["want"] = (cx, cy)
        entry["centre"] = (round(min(max(cx, half_w), 1920 - half_w), 1),
                           round(min(max(cy, half_h), 1080 - half_h), 1))
        entry["t"] = round(entry["t"], 3)
    return kept, dropped


def punch_filter(punches: list[dict]) -> str | None:
    """The single zoompan that plays every punch-in, or None when there is nothing to play.

    `on/30` is the time of the frame being written, which is the render's own clock because the
    stream is constant 30 fps by the time this runs. Each punch contributes a raised cosine, from 0
    at its start through 1 at its middle back to 0, flattened at the top so the move holds at 1.15x
    for about half a second instead of touching it for one frame. The pulses never overlap, so they
    can simply be summed.
    """
    if not punches:
        return None
    pulses, dxs, dys = [], [], []
    for punch in punches:
        start = punch["t"]
        cx, cy = punch["centre"]
        u = f"(on/30-{start:.3f})/{PUNCH_S}"
        pulse = f"between(on/30,{start:.3f},{start + PUNCH_S:.3f})*min(1,(1-cos(2*PI*{u}))/2*1.4)"
        pulses.append(f"({pulse})")
        dxs.append(f"({cx - 960:.1f})*({pulse})")
        dys.append(f"({cy - 540:.1f})*({pulse})")
    zoom = f"1+{PUNCH_ZOOM - 1:.4f}*({'+'.join(pulses)})"
    # The window is centred on the frame at rest and on the element at the top of the move, so the
    # picture never jumps sideways when a punch starts or ends.
    x = f"max(0,min((960+{'+'.join(dxs)})*zoom-960,iw*zoom-1920))"
    y = f"max(0,min((540+{'+'.join(dys)})*zoom-540,ih*zoom-1080))"
    return f"zoompan=z='{zoom}':x='{x}':y='{y}':d=1:s=1920x1080:fps=30"


def longest_dead_stretch(events: list[float], voice: list[tuple[float, float]],
                         total: float, moving: list[tuple[float, float]] | None = None,
                         step: float = 0.05) -> tuple[float, float]:
    """The longest run of render time with no change of picture and no line playing.

    An event is an instant the picture changes: a cut, an insert opening or closing, an overlay
    ending, a punch-in landing, a caption appearing, a cue of the take. A voice interval covers its
    whole length, and so does a `moving` interval, which is a stretch the picture is changing
    through rather than at: a dashboard gliding under the camera. The clip playing on the stage is
    deliberately NOT one of those, so a run's own dead seconds are counted in full.

    Returns (seconds, where it starts).
    """
    marks = sorted(t for t in events if 0.0 <= t <= total)
    speaking = sorted(list(voice) + list(moving or []))
    worst, worst_at, run_from = 0.0, 0.0, 0.0
    i = j = 0
    t = 0.0
    while t <= total:
        while i < len(marks) and marks[i] < t - step / 2:
            i += 1
        hit = i < len(marks) and marks[i] < t + step / 2
        while j < len(speaking) and speaking[j][1] < t:
            j += 1
        talking = j < len(speaking) and speaking[j][0] <= t <= speaking[j][1]
        if hit or talking:
            if t - run_from > worst:
                worst, worst_at = t - run_from, run_from
            run_from = t
        t = round(t + step, 3)
    if total - run_from > worst:
        worst, worst_at = total - run_from, run_from
    return round(worst, 2), round(worst_at, 2)


def srt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d},{int(round((secs % 1) * 1000)):03d}"


class CutPlan:
    """The ranges dropped from the take, in the take's own video time."""

    def __init__(self, head: float, cuts: list[tuple[float, float, str, str]]):
        self.head = head
        self.cuts = sorted(cuts)

    @property
    def removed(self) -> float:
        return self.head + sum(b - a for a, b, _, _ in self.cuts)

    @property
    def compressions(self) -> list[tuple[float, float, str, str]]:
        """The stretches of waiting taken out, the only cuts that carry an on-screen label."""
        return [(a, b, name, kind) for a, b, name, kind in self.cuts if kind in WAIT_LABEL]

    def map(self, t: float) -> float:
        out = t - self.head
        for a, b, _, _ in self.cuts:
            if t >= b:
                out -= b - a
            elif t > a:
                out -= t - a
        return max(0.0, out)

    def select_expr(self) -> str:
        ranges = [(0.0, self.head)] if self.head > 0.01 else []
        ranges += [(a, b) for a, b, _, _ in self.cuts if b - a > 0.01]
        if not ranges:
            return ""
        inside = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in ranges)
        return f"select='not({inside})'"


def build_windows(at: dict, lines: list[dict], inserts: list[dict] | None = None,
                  protect_voice: bool = True, wait_keep: float = WAIT_KEEP_S) -> list[dict]:
    """What may be shortened, most expendable first: the waits, then two holds.

    A hold is never cut below the voice line spoken over it while `protect_voice` holds, so a beat
    always stays on screen at least as long as what is said about it. `wait_keep` is how much of a
    rights wait survives its own cut, and script v5 fixes it at half a second: waiting is what the
    video is cutting for pace, so what stays of it is the glimpse the caption is about.
    """
    voice = {}
    for line in lines:
        voice[line["cue"]] = voice.get(line["cue"], 0.0) + line["duration_s"]

    def carried(a: float, b: float) -> float:
        return sum(d for cue, d in voice.items() if cue in at and a <= at[cue] < b)

    # When the narration stops talking, in the take's own time: the lines laid on their cues and
    # cascaded the way narrate.py and place() cascade them. A wait may only start once the line
    # about the beat that opened it has been said, or the cut would drop the picture that line is
    # describing out from under it.
    spoken_until: dict[str, float] = {}
    previous_end = 0.0
    for cue in sorted((c for c in voice if c in at), key=lambda c: at[c]):
        start = max(at[cue], previous_end + MIN_GAP_S if previous_end else 0.0)
        previous_end = start + voice[cue]
        spoken_until[cue] = previous_end

    def quiet_from(cue: str) -> float:
        """The first moment after `cue` at which nothing is being said."""
        return max(at[cue], max((end for c, end in spoken_until.items() if at[c] <= at[cue]),
                                default=at[cue]))

    def window(a: float, b: float, keep: float, name: str, kind: str) -> dict | None:
        held = carried(a, b) if protect_voice else 0.0
        floor = max(keep, held + 0.5) if held else keep
        if b - a <= floor:
            return None
        return {"name": name, "a": a, "b": b, "keep": floor, "max": (b - a) - floor, "kind": kind}

    def span(start: str, end: str, keep: float, name: str) -> dict | None:
        if start not in at or end not in at:
            return None
        return window(at[start], at[end], keep, name, "hold")

    def rights_wait(suffix: str, name: str, keep: float = wait_keep) -> dict | None:
        """The wait on the rights gate: from the last of the other three to rights itself.

        This is the only stretch of a run the assembler is allowed to remove, and the only one
        the Video Intelligence call is responsible for. Reading it from the rights landing rather
        than from "the last chip to settle" keeps the label honest even on a run where some other
        gate happens to finish last.

        The wait starts once the line about the gate that landed last has been said (script v6;
        draft 5 started it at the landing itself, which pushed the rights line seven seconds off
        the rights landing because the claim line was still running when the cut brought the
        landing forward). What is removed is still nothing but waiting: the clip playing under a
        row that reads "Checking" while nobody speaks. A wait is not given the voice floor a hold
        gets: the line spoken over the settled chip starts at the cut point and that chip stays.
        """
        rights = at.get(f"rights_done{suffix}")
        others = [(at[f"{g}_done{suffix}"], g) for g in ("claim", "brand", "provenance")
                  if f"{g}_done{suffix}" in at]
        before = [o for o in others if o[0] < rights] if rights is not None else []
        if rights is None or not before:
            return None
        (a, last_gate), b = max(before), rights
        a = max(a, quiet_from(f"{last_gate}_done{suffix}"))
        seek = at.get("seek_claim")
        if seek is not None and a <= seek < b:
            # The recorder logs seek_done when it is back on the Checks segment; before that cue
            # existed the beat was given a fixed SEEK_BEAT_S, which is still the fallback.
            a = min(max(a, at.get("seek_done", seek + SEEK_BEAT_S)), b)
        if b - a <= keep:
            return None
        return {"name": name, "a": a, "b": b, "keep": keep, "max": (b - a) - keep,
                "kind": "run_wait"}

    def grafana_wait(insert: dict, keep: float = wait_keep) -> dict | None:
        """The wait for a Grafana insert to draw, from the page opening to `<name>_ready`.

        The insert itself starts at `ready_at`, so these seconds are not Grafana on screen: they
        are the console take holding on a card that has already settled while a second tab loads
        behind it. That is waiting, the same as the rights gate's, so it is cut the same way and
        announced the same way, and half a second of it stays on the picture like every other wait.
        """
        a, b = insert.get("open_s"), insert.get("ready_s")
        if a is None or b is None or b - a <= keep:
            return None
        return {"name": insert["name"], "a": a, "b": b, "keep": keep, "max": (b - a) - keep,
                "kind": "grafana_wait"}

    def gate_waits(suffix: str) -> list[dict]:
        """Between two landings of the same run: one gate's line has been said, the next has not
        landed yet, and the picture is a clip playing under a row that reads "Checking".

        The last pair of a run is the rights gate's own wait, which `rights_wait` already names
        after the call it is blocked on, so it is not repeated here.
        """
        landed = sorted((at[f"{g}_done{suffix}"], g) for g in GATE_ORDER
                        if f"{g}_done{suffix}" in at)
        out = []
        for (t_prev, prev), (t_next, gate) in zip(landed, landed[1:], strict=False):
            if gate == "rights":
                continue
            a = max(quiet_from(f"{prev}_done{suffix}"), t_prev)
            seek = at.get("seek_claim")
            if seek is not None and a <= seek < t_next:
                a = min(at.get("seek_done", seek + SEEK_BEAT_S), t_next)
            if t_next - a <= wait_keep + SMALL_WAIT_S:
                continue
            out.append({"name": f"waiting for the {gate} gate{suffix}", "a": a, "b": t_next,
                        "keep": wait_keep, "max": (t_next - a) - wait_keep, "kind": "gate_wait",
                        "gate": gate})
        return out

    def investigation_wait(suffix: str) -> dict | None:
        """After the verdict line has been said and before the escalation lands: the investigator
        is still reading Loki, the row under the card names its tool calls, nothing else moves."""
        start, end = at.get(f"verdict{suffix}"), at.get(f"escalation_done{suffix}")
        if start is None or end is None:
            return None
        a = max(quiet_from(f"verdict{suffix}"), start)
        if end - a <= wait_keep + SMALL_WAIT_S:
            return None
        return {"name": f"waiting for the investigator{suffix}", "a": a, "b": end,
                "keep": wait_keep, "max": (end - a) - wait_keep, "kind": "investigation_wait"}

    def verdict_wait(suffix: str) -> dict | None:
        """The seconds between the last gate landing and the verdict card: the verdict agent
        asking Grafana about each gate before it rules."""
        last = max((at[f"{g}_done{suffix}"] for g in GATE_ORDER if f"{g}_done{suffix}" in at),
                   default=None)
        end = at.get(f"verdict{suffix}")
        if last is None or end is None:
            return None
        # Strictly before the card fills: the line spoken over the verdict itself starts there and
        # is the reason the hold exists, so it must not close the window it opens.
        a = max(last, max((v for c, v in spoken_until.items() if at[c] < end), default=last))
        if end - a <= wait_keep + SMALL_WAIT_S:
            return None
        return {"name": f"waiting for the verdict agent{suffix}", "a": a, "b": end,
                "keep": wait_keep, "max": (end - a) - wait_keep, "kind": "verdict_wait"}

    candidates = [
        # Only waiting is ever taken out, and each stretch is announced on the picture: the rights
        # gate's calls to Video Intelligence, the seconds between two landings, the verdict agent
        # asking Grafana, a Grafana insert drawing. The holds below are the overflow, in that
        # order, and only when the waits alone cannot bring the render under the maximum.
        rights_wait("", "Crest run, waiting for Video Intelligence"),
        rights_wait("_2", "fault run, waiting for Video Intelligence"),
        rights_wait("_3", "study run, waiting for Video Intelligence"),
        *gate_waits(""),
        *gate_waits("_2"),
        *gate_waits("_3"),
        verdict_wait(""),
        verdict_wait("_2"),
        verdict_wait("_3"),
        # The third run's investigator works under the dashboard insert, which is not waiting, so
        # only the first two runs carry this window.
        investigation_wait(""),
        investigation_wait("_2"),
        *(grafana_wait(insert) for insert in (inserts or [])),
        span("dashboard", "landing", 5.0, "dashboard hold"),
        span("landing", "end", 6.7, "landing hold"),
    ]
    return [w for w in candidates if w]


def plan_for(trim: float, head: float, windows: list[dict]) -> CutPlan:
    """Spend the requested trim on the windows in order, each from its start.

    Nothing under a second is ever taken: the caption announcing a cut names the number of whole
    seconds it removes, so half a second of leftover trim spent on a window would put "0 s
    compressed" on the picture. The leftover is left in the render instead, which costs it under
    a second of length and keeps every caption true.
    """
    cuts, left = [], trim
    for window in windows:
        if left < 1.0:
            break
        take = min(left, window["max"])
        if take < 1.0:
            continue
        cuts.append((window["a"], window["a"] + take, window["name"], window["kind"]))
        left -= take
    return CutPlan(head, cuts)


def place(lines: list[dict], plan: CutPlan, offset: float) -> list[dict]:
    placed = []
    previous_end = 0.0
    for line in sorted(lines, key=lambda entry: entry.get("cue_t", entry["start_s"])):
        wanted = plan.map(line.get("cue_t", line["start_s"]) - offset)
        floor = previous_end + MIN_GAP_S if previous_end else 0.0
        start = max(wanted, floor)
        entry = dict(line)
        entry["start_final_s"] = round(start, 3)
        entry["shift_final_s"] = round(start - wanted, 3)
        entry["end_final_s"] = round(start + line["duration_s"], 3)
        placed.append(entry)
        previous_end = start + line["duration_s"]
    return placed


def room_tone_gain(target_dbfs: float) -> float:
    """Measure a pink noise source once so the tone lands at a known level."""
    out = run(
        ["ffmpeg", "-nostdin", "-f", "lavfi", "-i", "anoisesrc=c=pink:r=48000:a=0.1:d=4",
         "-af", "lowpass=f=1800,volumedetect", "-f", "null", "-"]
    )
    match = re.search(r"mean_volume:\s*(-?[\d.]+) dB", out.stderr)
    if not match:
        return 0.0
    return target_dbfs - float(match.group(1))


def loudnorm_pass(path: Path) -> dict:
    out = run(["ffmpeg", "-nostdin", "-i", str(path), "-af",
               "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    match = re.search(r"\{[^{}]*input_i[^{}]*\}", out.stderr, re.S)
    if not match:
        raise SystemExit("loudnorm could not measure the narration mix")
    return json.loads(match.group(0))


def build_audio(lines: list[dict], out_dir: Path, total: float, tone_db: float) -> Path:
    """Sum the wav files at their final positions, normalise, then lay a room tone under it."""
    raw = out_dir / "narration-raw.wav"
    inputs, filters, labels = [], [], []
    for i, line in enumerate(lines):
        inputs += ["-i", str(out_dir / line["wav"])]
        delay = int(round(line["start_final_s"] * 1000))
        filters.append(f"[{i}:a]aresample=48000,adelay={delay}|{delay},apad[v{i}]")
        labels.append(f"[v{i}]")
    filters.append(f"{''.join(labels)}amix=inputs={len(lines)}:normalize=0:dropout_transition=0[mix]")
    cmd = ["ffmpeg", "-y", "-nostdin", *inputs, "-filter_complex", ";".join(filters),
           "-map", "[mix]", "-t", f"{total:.3f}", "-ac", "1", "-ar", "48000", str(raw)]
    result = run(cmd)
    if not raw.exists():
        raise SystemExit(f"the narration mix failed:\n{result.stderr[-2000:]}")

    measured = loudnorm_pass(raw)
    gain = room_tone_gain(tone_db)
    final = out_dir / "narration-mix.wav"
    norm = (
        "loudnorm=I=-16:TP=-1.5:LRA=11"
        f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        ":linear=true:print_format=summary"
    )
    cmd = [
        "ffmpeg", "-y", "-nostdin", "-i", str(raw),
        "-f", "lavfi", "-i", f"anoisesrc=c=pink:r=48000:a=0.1:d={total + 1:.3f}",
        "-filter_complex",
        f"[0:a]{norm}[voice];[1:a]volume={gain:.2f}dB,lowpass=f=1800[tone];"
        "[voice][tone]amix=inputs=2:normalize=0:dropout_transition=0[out]",
        "-map", "[out]", "-t", f"{total:.3f}", "-ac", "2", "-ar", "48000", str(final),
    ]
    result = run(cmd)
    if not final.exists():
        raise SystemExit(f"the normalised mix failed:\n{result.stderr[-2000:]}")
    return final


def write_srt(lines: list[dict], path: Path) -> list[dict]:
    """One subtitle block per sentence, not per spoken line. Returns the cues it wrote."""
    cues = [cue for line in lines for cue in subtitle_cues(line)]
    blocks = []
    for i, cue in enumerate(cues, start=1):
        text = "\n".join(wrap(cue["text"], SUBTITLE_WIDTH))
        blocks.append(f"{i}\n{srt_time(cue['start'])} --> {srt_time(cue['end'])}\n{text}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")
    return cues


def build_video(
    console: Path, overlays: list[dict], plan: CutPlan, total: float, raw_len: float,
    out_dir: Path, srt: Path, audio: Path, target: Path, subtitle_size: int,
    labels: list[dict], punch: str | None = None, voice_caption: str | None = None,
) -> None:
    a50 = out_dir / "article-50.txt"
    a50.write_text("\n".join(wrap(ARTICLE_50, 58)) + "\n", encoding="utf-8")

    inputs = ["-i", str(console)]
    for overlay in overlays:
        inputs += ["-i", str(overlay["path"])]

    steps = ["[0:v]fps=30,scale=1920:1080:flags=lanczos,setsar=1[base]"]
    current = "[base]"
    for i, overlay in enumerate(overlays, start=1):
        start, end = overlay["window"]
        skip = overlay.get("skip", 0.0)
        head = f"trim=start={skip:.3f},setpts=PTS-STARTPTS," if skip > 0.05 else ""
        steps.append(f"[{i}:v]{head}fps=30,scale=1920:1080:flags=lanczos,setsar=1,"
                     f"setpts=PTS-STARTPTS+{start:.3f}/TB[ov{i}]")
        steps.append(f"{current}[ov{i}]overlay=0:0:eof_action=pass:enable='between(t,{start:.3f},{end:.3f})'[b{i}]")
        current = f"[b{i}]"

    chain = []
    select = plan.select_expr()
    if select:
        chain.append(select)
    chain.append("setpts=N/30/TB")
    pad = total - (raw_len - plan.removed)
    if pad > 0.05:
        chain.append(f"tpad=stop_mode=clone:stop_duration={pad + 0.5:.3f}")
    # The punch-ins run on the picture only. Everything burned in below (the Article 50 overlay,
    # the compression captions, the subtitles) is drawn after them and never moves.
    if punch:
        chain.append("format=yuv444p")
        chain.append(punch)
    chain.append(
        f"drawtext=fontfile={FONT}:textfile={a50}:fontsize=40:fontcolor=white:line_spacing=10"
        ":box=1:boxcolor=black@0.78:boxborderw=32:x=(w-text_w)/2:y=(h-text_h)/2-90"
        f":alpha='if(lt(t,{ARTICLE_50_S - 1.5:.1f}),1,max(0,({ARTICLE_50_S:.1f}-t)/1.5))'"
        f":enable='between(t,0,{ARTICLE_50_S:.1f})'"
    )
    # Every compressed wait says so on the picture, in the seconds that run up to the cut.
    for i, label in enumerate(labels, start=1):
        caption = out_dir / f"compression-{i}.txt"
        caption.write_text(label["text"], encoding="utf-8")
        chain.append(
            f"drawtext=fontfile={MONO_FONT}:textfile={caption}"
            f":fontsize={COMPRESSION_FONT_SIZE}:fontcolor=white:box=1:boxcolor=black@0.78"
            ":boxborderw=16:x=(w-text_w)/2:y=42"
            f":enable='between(t,{label['from']:.3f},{label['to']:.3f})'"
        )
    if voice_caption:
        caption = out_dir / "voice-caption.txt"
        caption.write_text(voice_caption, encoding="utf-8")
        windows = f"between(t,0,{VOICE_CAPTION_S:.1f})+between(t,{total - VOICE_CAPTION_END_S:.3f},{total:.3f})"
        chain.append(
            f"drawtext=fontfile={MONO_FONT}:textfile={caption}"
            f":fontsize={VOICE_CAPTION_FONT_SIZE}:fontcolor=white:box=1:boxcolor=black@0.78"
            f":boxborderw=12:x=w-text_w-24:y=12:enable='{windows}'"
        )
    chain.append(
        f"subtitles={srt}:force_style='FontName=Arial,FontSize={subtitle_size},"
        "PrimaryColour=&H00FFFFFF,BackColour=&HB4000000,BorderStyle=4,Outline=0,Shadow=0,"
        "Alignment=2,MarginV=28'"
    )
    chain.append("format=yuv420p")
    steps.append(f"{current}{','.join(chain)}[v]")

    cmd = [
        "ffmpeg", "-y", "-nostdin", *inputs, "-i", str(audio),
        "-filter_complex", ";".join(steps),
        "-map", "[v]", "-map", f"{len(overlays) + 1}:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-r", "30", "-vsync", "cfr", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", "-t", f"{total:.3f}", str(target),
    ]
    (out_dir / "logs").mkdir(exist_ok=True)
    (out_dir / "logs" / "ffmpeg-assemble.cmd").write_text(" ".join(cmd) + "\n", encoding="utf-8")
    result = run(cmd)
    (out_dir / "logs" / "ffmpeg-assemble.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0 or not target.exists():
        raise SystemExit(f"ffmpeg failed:\n{result.stderr[-4000:]}")


def next_draft(out_dir: Path) -> int:
    used = [int(m.group(1)) for m in
            (re.match(r"airlock-draft-(\d+)-synthetic-voice\.mp4$", p.name) for p in out_dir.glob("*.mp4")) if m]
    return max(used, default=0) + 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "video" / "out"))
    ap.add_argument("--draft", type=int, default=None)
    ap.add_argument("--output", default=None,
                    help="file name of the render inside --out (default: airlock-draft-<n>-synthetic-voice.mp4)")
    # The cut aims at nothing: it removes all the waiting and reports where that lands. --min is
    # the length the render is expected to reach and only ever prints a warning; --max is the one
    # number with teeth, because past it a hold gets shortened.
    ap.add_argument("--min", dest="minimum", type=float, default=150.0)
    ap.add_argument("--max", dest="maximum", type=float, default=170.0)
    # libass scales the style of an SRT from a 384x288 script box, so a size lands on screen at
    # roughly 3.75 times its number: 13 renders about 49 px tall at 1080p, which is the intent of
    # the brief's "size 26". Passing 26 itself fills a third of the frame.
    ap.add_argument("--subtitle-size", type=int, default=13)
    ap.add_argument("--tone-dbfs", type=float, default=ROOM_TONE_DBFS)
    ap.add_argument("--no-check", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out)
    take = json.loads((out_dir / "cues.json").read_text(encoding="utf-8"))
    narration = json.loads((out_dir / "narration.json").read_text(encoding="utf-8"))

    console = out_dir / take["video"]
    raw_len = duration_of(console)
    at = {}
    for entry in take["cues"]:
        at.setdefault(entry["cue"], float(entry["t"]))

    # The context video starts a fraction of a second after the recorder's own clock, so every cue
    # is read back through that offset before anything is cut.
    offset = min(max(at.get("end", raw_len) - raw_len, 0.0), 6.0)
    at_video = {cue: max(0.0, t - offset) for cue, t in at.items()}
    at_video["end"] = raw_len

    overlays = []
    for entry in take.get("overlays", []):
        path = out_dir / "raw" / entry["file"]
        if not path.exists():
            print(f"overlay {entry['file']} is missing, the console take plays through instead")
            continue
        length = duration_of(path)
        # The insert starts where the recorder saw the panels draw, so no loading dashboard and no
        # blank tab ever reaches the render; the console take, with the verdict on it, plays
        # underneath until then. The black head is the fallback for a page whose panels never drew.
        skip, source = leading_black(path), "blank tab"
        ready, closed = entry.get("ready_at"), entry["closed_at"]
        if ready is not None and closed - ready > 0.5:
            wanted = length - (closed - ready)
            if wanted > skip + 0.05:
                skip, source = wanted, f"{entry.get('ready_cue', 'the ready cue')} (panels drawn)"
        if skip > length - 1.0:
            skip, source = 0.0, "nothing skipped"
        end = max(0.0, closed - offset)
        overlays.append({"path": path, "skip": skip, "source": source, "cue": entry["cue"],
                         "window": (max(0.0, end - (length - skip)), end),
                         "open_s": max(0.0, entry["page_opened_at"] - offset),
                         "ready_s": None if ready is None else max(0.0, ready - offset),
                         "glide_s": (None if entry.get("glide_from") is None
                                     else max(0.0, entry["glide_from"] - offset)),
                         "glide_to_s": (None if entry.get("glide_to") is None
                                        else max(0.0, entry["glide_to"] - offset)),
                         "name": f"{entry['cue']} insert, waiting for Grafana"})
        if skip > 0.05:
            print(f"overlay {entry['cue']}: {length:.1f}s recorded, skipping {skip:.1f}s of its "
                  f"head on {source}, {length - skip:.1f}s on screen")

    head = max(0.0, at_video.get("stake", 0.0) - 0.4)

    def measure(plan: CutPlan) -> dict:
        placed = place(narration["lines"], plan, offset)
        narration_end = max(line["end_final_s"] for line in placed)
        video_len = raw_len - plan.removed
        return {"plan": plan, "placed": placed, "video_len": video_len,
                "narration_end": narration_end,
                "total": max(video_len, narration_end + TAIL_PAD_S)}

    def search(windows: list[dict]) -> dict:
        """Compress every wait, then only as much of a hold as the length limit demands.

        Draft 4 looked for the trim that landed closest to a target, which could leave half a wait
        on the picture to make the numbers work: twenty seconds of a settled card and no voice,
        which is exactly what this cut is against. So the waits now always come off whole, down to
        the half second the caption promises, and a hold is only ever touched to get back under the
        maximum. Nothing is ever padded to reach a length: a render that lands short lands short
        and says so.
        """
        waits = [w for w in windows if w["kind"] in WAIT_LABEL]
        holds = sum(w["max"] for w in windows if w["kind"] not in WAIT_LABEL)

        def with_waits(cut: list[dict], extra: float = 0.0) -> dict:
            chosen = cut + [w for w in windows if w["kind"] not in WAIT_LABEL]
            trim = sum(w["max"] for w in cut) + extra
            out = measure(plan_for(trim, head, chosen))
            out.update(trim=trim, windows=chosen)
            return out

        best = with_waits(waits)

        def short(out: dict) -> bool:
            """The render is under the floor, or the picture ends before the voice does and the
            last frame would be cloned to cover the difference."""
            return (out["total"] < args.minimum
                    or out["video_len"] < out["narration_end"] + TAIL_PAD_S - 0.05)

        # Under the floor, or with the voice outlasting the picture, whole waits go back on the
        # picture, the shortest first, until neither holds. A wait is never given back in part:
        # what is cut is cut to the half second the caption promises, and what is kept is kept
        # whole.
        if short(best):
            cut = list(waits)
            for window in sorted(waits, key=lambda w: w["max"]):
                if not short(best) or window["max"] > GIVE_BACK_MAX_S:
                    break
                attempt = with_waits([w for w in cut if w is not window])
                if attempt["total"] > args.maximum:
                    break
                cut = [w for w in cut if w is not window]
                best = attempt
        if best["total"] <= args.maximum:
            return best
        for extra_tenths in range(5, int(holds * 10) + 1, 5):
            attempt = with_waits(waits, extra_tenths / 10)
            best = attempt
            if attempt["total"] <= args.maximum:
                break
        return best

    # Two passes, the second giving up less than the first. The waits come off whole in both,
    # because they are the only stretch the script allows the assembler to remove, and half a
    # second of each survives in both: that is what the picture shows behind the caption. What the
    # second pass gives up is the floor that protected the line spoken over a hold.
    attempts = [
        (f"every wait compressed to {WAIT_KEEP_S:.1f} s, the two holds protected",
         dict(protect_voice=True)),
        ("the two holds giving up the floor that protected the line spoken over them",
         dict(protect_voice=False)),
    ]
    best = None
    for label, kwargs in attempts:
        best = search(build_windows(at_video, narration["lines"], overlays, **kwargs))
        if best["total"] <= args.maximum:
            print(f"cut plan: {label}")
            break
        print(f"over {args.maximum:.0f}s with {label}, trying the next plan")

    plan, placed, total = best["plan"], best["placed"], best["total"]
    print(f"take {raw_len:.1f}s, head trim {head:.1f}s, cut {best['trim']:.1f}s, "
          f"video {best['video_len']:.1f}s, narration ends {best['narration_end']:.1f}s, "
          f"render {total:.1f}s")
    if total < args.minimum:
        print(f"  the picture is {total:.1f}s, under the {args.minimum:.0f}s target floor: the "
              f"take is what it is and no hold is padded to reach a length")
    frozen = best["narration_end"] + TAIL_PAD_S - best["video_len"]
    if frozen > 0.05:
        print(f"  the voice outlasts the picture by {frozen:.1f}s: the last frame is held that long")
    if total > args.maximum:
        print(f"  the picture is {total:.1f}s, over the {args.maximum:.0f}s target ceiling with "
              f"everything this cut is allowed to remove")

    compressions = []
    labels = []
    by_name = {window["name"]: window for window in best["windows"]}
    for a, b, name, kind in plan.compressions:
        removed = int(round(b - a))
        at_cut = plan.map(a)
        text = WAIT_LABEL[kind].format(n=removed, gate=by_name.get(name, {}).get("gate", ""))
        compressions.append({"start_take_s": round(a, 3), "end_take_s": round(b, 3),
                             "removed_s": removed, "name": name, "kind": kind, "label": text,
                             "at_render_s": round(at_cut, 3)})
        labels.append({
            "text": text,
            "from": max(0.0, at_cut - COMPRESSION_LABEL_S),
            "to": at_cut,
        })
    # Two cuts can land close enough that their captions would be drawn on top of each other, in
    # the same place, at the same size, for the second it takes to read either. The later one waits
    # for the earlier to have said what it says.
    labels.sort(key=lambda label: label["to"])
    for previous, label in zip(labels, labels[1:], strict=False):
        if label["from"] < previous["to"]:
            label["from"] = min(previous["to"], label["to"] - 0.5)
    held_back = sum(b - a for a, b, _, kind in plan.cuts if kind not in WAIT_LABEL)

    for a, b, name, kind in plan.cuts:
        marker = "labelled" if kind in WAIT_LABEL else "hold"
        print(f"  cut {b - a:5.1f}s from the {name}  ({marker})")
    if held_back > 0.05:
        print(f"  the waits alone left the picture at "
              f"{best['video_len'] + held_back:.1f}s, so {held_back:.1f}s more came off the "
              f"dashboard and landing holds")
    for line in placed:
        print(f"  {line['cue']:<20} {line['start_final_s']:7.2f}s to {line['end_final_s']:7.2f}s"
              f"  (+{line['shift_final_s']:.2f}s)")

    # The punch-ins, in the render's own time, and then the measurement the whole cut is for: the
    # longest stretch with neither a change of picture nor a line playing.
    at_render = {cue: plan.map(t) for cue, t in at_video.items()}
    punches, punches_dropped = build_punches(at_render, total)
    punch = punch_filter(punches)
    print(f"{len(punches)} punch-ins of {PUNCH_ZOOM}x over {PUNCH_S}s")
    for entry in punches:
        cx, cy = entry["centre"]
        wx, wy = entry["want"]
        clamp = "" if (cx, cy) == (wx, wy) else f"  (asked for {wx},{wy}, 1.15x reaches this far)"
        print(f"  {entry['t']:7.2f}s  {entry['cue']:<20} {entry['target']:<8} at {cx},{cy}{clamp}")
    for entry in punches_dropped:
        print(f"  dropped {entry['cue']} at {entry['t']:.2f}s: {entry['why']}")

    picture_events = (
        [t for t in at_render.values() if 0.0 <= t <= total]
        + [plan.map(a) for a, _, _, _ in plan.cuts]
        + [entry["t"] for entry in punches]
        + [label["from"] for label in labels]
        + [ARTICLE_50_S]
        + [t for overlay in overlays for t in (plan.map(overlay["window"][0]),
                                               plan.map(overlay["window"][1]))]
    )
    voice_spans = [(line["start_final_s"], line["end_final_s"]) for line in placed]
    glides = [(plan.map(overlay["glide_s"]), plan.map(overlay["glide_to_s"]))
              for overlay in overlays
              if overlay.get("glide_s") is not None and overlay.get("glide_to_s") is not None]
    dead_s, dead_at = longest_dead_stretch(picture_events, voice_spans, total, glides)
    print(f"longest stretch with no change of picture and no voice: {dead_s:.2f}s at {dead_at:.1f}s")

    srt = out_dir / "narration.srt"
    subtitles = write_srt(placed, srt)
    print(f"{len(subtitles)} subtitle cues over {len(placed)} spoken lines")

    number = args.draft if args.draft is not None else next_draft(out_dir)
    target = out_dir / (args.output or f"airlock-draft-{number}-synthetic-voice.mp4")
    voice_caption = None
    if narration.get("synthetic"):
        voice_caption = (f"synthetic voice: Google Cloud Text to Speech, {narration.get('voice', 'unknown voice')}"
                         f" at {narration.get('speaking_rate', 1.0)}x")
        print(f"voice caption over the first {VOICE_CAPTION_S:.0f} s and the last {VOICE_CAPTION_END_S:.0f} s: {voice_caption}")

    tone = args.tone_dbfs
    verdict_lines: list[str] = []
    for attempt in range(1, 4):
        audio = build_audio(placed, out_dir, total, tone)
        build_video(console, overlays, plan, total, raw_len, out_dir, srt, audio, target,
                    args.subtitle_size, labels, punch, voice_caption)
        size_mb = target.stat().st_size / 1024 / 1024
        print(f"\nwrote {target} ({size_mb:.1f} MB)")
        if args.no_check:
            break
        checker = render_checker()
        if checker is None:
            if not os.environ.get(RENDER_CHECK_ENV, "").strip():
                print("render check skipped, no checker configured")
            break
        result = run(["python3", str(checker), "--render", str(target), "--limit-s", "180"])
        verdict_lines = (result.stdout or "").splitlines()
        print("\n".join(verdict_lines))
        if "FAIL" not in result.stdout:
            break
        if re.search(r"FAIL\s+G46", result.stdout) and attempt < 3:
            tone += 5.0
            print(f"\nsilence still detected, raising the room tone to {tone:.0f} dBFS and rebuilding")
            continue
        break

    summary = {
        "draft": None if args.output else number,
        "output": target.name,
        "voice_caption": voice_caption,
        "mp4": str(target),
        "duration_s": round(total, 3),
        "take_s": round(raw_len, 3),
        "offset_s": round(offset, 3),
        "head_trim_s": round(head, 3),
        "cuts": [{"name": name, "kind": kind, "from_s": round(a, 2), "to_s": round(b, 2)}
                 for a, b, name, kind in plan.cuts],
        "compressions": [{"start_take_s": c["start_take_s"], "end_take_s": c["end_take_s"],
                          "removed_s": c["removed_s"], "kind": c["kind"], "label": c["label"]}
                         for c in compressions],
        "compression_labels": [{"text": label["text"], "from_s": round(label["from"], 3),
                                "to_s": round(label["to"], 3)} for label in labels],
        "hold_trim_s": round(held_back, 3),
        "voice_outlasts_picture_s": round(max(0.0, best["narration_end"] + TAIL_PAD_S - best["video_len"]), 3),
        "punches": [{"cue": entry["cue"], "target": entry["target"], "at_s": entry["t"],
                     "centre": list(entry["centre"]), "wanted_centre": list(entry["want"]),
                     "zoom": PUNCH_ZOOM, "seconds": PUNCH_S} for entry in punches],
        "punches_dropped": [{"cue": entry["cue"], "at_s": round(entry["t"], 3),
                             "why": entry["why"]} for entry in punches_dropped],
        "pace": {"longest_no_picture_no_voice_s": dead_s, "starts_at_s": dead_at,
                 "voice_s": round(sum(b - a for a, b in voice_spans), 2),
                 "picture_events": len(set(round(t, 2) for t in picture_events))},
        "overlays": [{"cue": o["cue"], "from_s": round(plan.map(o["window"][0]), 2),
                      "to_s": round(plan.map(o["window"][1]), 2),
                      "head_skipped_s": round(o["skip"], 2),
                      "head_skipped_on": o["source"]} for o in overlays],
        "room_tone_dbfs": tone,
        "lines": [{k: line[k] for k in ("cue", "start_final_s", "end_final_s", "shift_final_s", "text")}
                  for line in placed],
        "subtitles": [{"text": cue["text"], "start_s": round(cue["start"], 3),
                       "end_s": round(cue["end"], 3)} for cue in subtitles],
        "check": verdict_lines,
    }
    (out_dir / "assembly.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
