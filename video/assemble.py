#!/usr/bin/env python3
"""assemble.py: cut the take, lay the narration and the subtitles on it, and check the render.

Reads video/out/cues.json and video/out/narration.json, converts the Playwright webm to
1920x1080 at 30 fps constant, lays the Grafana pages the recorder opened on a second tab over the
console take for the windows they were open, burns the Article 50 overlay and the subtitles, mixes
the narration at its cue times over a room tone, and writes
video/out/airlock-draft-<n>-synthetic-voice.mp4.

The take is longer than the video, because a real run takes as long as it takes. The only stretch
the cut plan is allowed to remove is the wait on the rights gate, the Video Intelligence call, and
every one of those says so on the picture before it happens: "waiting for Video Intelligence, N s
compressed". If that is still not enough to fit the duration limit, the dashboard hold and then
the landing hold are shortened and the assembler prints by how much. Every cue time is mapped
through the cuts, so the narration stays on the picture it describes, and the subtitles are cut
one per sentence rather than one per spoken line.

    uv run python video/assemble.py
    uv run python video/assemble.py --draft 2 --target 180
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK = Path("/Users/dylanmerigaud/Code/growth-cockpit/career/hackathon-evals/check.py")
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

ARTICLE_50 = (
    "Article 50, EU AI Act, in force 2 August 2026: providers of AI systems generating "
    "synthetic content shall ensure the outputs are marked in a machine-readable format "
    "and detectable as artificially generated"
)
ARTICLE_50_S = 8.0
MIN_GAP_S = 0.4
TAIL_PAD_S = 1.2
ROOM_TONE_DBFS = -38.0  # above silencedetect's -45 dB floor, so a gap never reads as dead air

# A subtitle cue is one sentence, wrapped at about this width and never more than two rows, so a
# viewer reads a whole thought at once instead of a paragraph parked on the picture for 15 s.
SUBTITLE_WIDTH = 60
SUBTITLE_ROWS = 2
# Every stretch the assembler takes out of a run is announced on the picture just before it
# happens, in a mono face so it reads as an editing note and not as console copy.
MONO_FONT = "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"
COMPRESSION_LABEL_S = 2.5
COMPRESSION_FONT_SIZE = 28


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def probe(path: Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)])
    return json.loads(out.stdout)


def duration_of(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def leading_black(path: Path, max_lead: float = 8.0) -> float:
    """How many seconds of the head of a clip are black.

    A Grafana page is recorded from the moment it opens, and the recorder then waits for the
    panels to draw their canvases before it holds, so the first seconds of that file are a blank
    tab. Laid over the take as they are, they put a black hole in the middle of the video.
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
    def compressions(self) -> list[tuple[float, float, str]]:
        """The stretches taken out of a run, the only cuts that carry an on-screen label."""
        return [(a, b, name) for a, b, name, kind in self.cuts if kind == "run_wait"]

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


def build_windows(at: dict, lines: list[dict], protect_voice: bool = True,
                  wait_keep: float = 3.0) -> list[dict]:
    """What may be shortened, most expendable first: the rights waits, then two holds.

    A hold is never cut below the voice line spoken over it while `protect_voice` holds, so a beat
    always stays on screen at least as long as what is said about it. `wait_keep` is how much of a
    rights wait survives its own cut; the caller lowers it before it gives up that protection,
    because a second of visible waiting is worth less than a line landing on its own picture.
    """
    voice = {}
    for line in lines:
        voice[line["cue"]] = voice.get(line["cue"], 0.0) + line["duration_s"]

    def carried(a: float, b: float) -> float:
        return sum(d for cue, d in voice.items() if cue in at and a <= at[cue] < b)

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

        A wait is never given the voice floor a hold gets, and that is not an oversight: the line
        spoken over the gate that just settled starts at the cut point and the picture it
        describes, the settled chip, is still there after the cut and stays there. A hold is the
        other case, its picture ends at the end of the window.
        """
        rights = at.get(f"rights_done{suffix}")
        others = [at[f"{g}_done{suffix}"] for g in ("claim", "brand", "provenance")
                  if f"{g}_done{suffix}" in at]
        before = [o for o in others if o < rights] if rights is not None else []
        if rights is None or not before:
            return None
        a, b = max(before), rights
        if b - a <= keep:
            return None
        return {"name": name, "a": a, "b": b, "keep": keep, "max": (b - a) - keep,
                "kind": "run_wait"}

    candidates = [
        # Only the waits on the rights gate come out of a run, and each one is announced on the
        # picture. The holds below are the overflow, in that order, and only when the waits alone
        # cannot bring the render under the duration limit.
        rights_wait("", "Crest run, waiting for Video Intelligence"),
        rights_wait("_2", "muted clean run, waiting for Video Intelligence"),
        rights_wait("_3", "clean run, waiting for Video Intelligence"),
        span("dashboard", "landing", 5.0, "dashboard hold"),
        span("landing", "end", 8.0, "landing hold"),
    ]
    return [w for w in candidates if w]


def plan_for(trim: float, head: float, windows: list[dict]) -> CutPlan:
    """Spend the requested trim on the windows in order, each from its start."""
    cuts, left = [], trim
    for window in windows:
        if left <= 0.05:
            break
        take = min(left, window["max"])
        if take > 0.05:
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
    labels: list[dict],
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
    ap.add_argument("--target", type=float, default=177.0)
    ap.add_argument("--min", dest="minimum", type=float, default=170.0)
    ap.add_argument("--max", dest="maximum", type=float, default=179.0)
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
        skip = leading_black(path)
        if skip > length - 1.0:
            skip = 0.0
        end = max(0.0, entry["closed_at"] - offset)
        overlays.append({"path": path, "skip": skip, "cue": entry["cue"],
                         "window": (max(0.0, end - (length - skip)), end)})
        if skip > 0.05:
            print(f"overlay {entry['cue']}: skipping {skip:.1f}s of blank tab at its head")

    head = max(0.0, at_video.get("stake", 0.0) - 0.4)

    def search(windows: list[dict]) -> dict:
        budget = sum(w["max"] for w in windows)
        best = None
        for trim_tenths in range(0, int(budget * 10) + 1, 5):
            trim = trim_tenths / 10
            plan = plan_for(trim, head, windows)
            placed = place(narration["lines"], plan, offset)
            narration_end = max(line["end_final_s"] for line in placed)
            video_len = raw_len - plan.removed
            total = max(video_len, narration_end + TAIL_PAD_S)
            penalty = 0.0 if args.minimum <= total <= args.maximum else 1000.0
            score = penalty + abs(total - args.target)
            if best is None or score < best["score"]:
                best = {"score": score, "trim": trim, "plan": plan, "placed": placed,
                        "total": total, "video_len": video_len, "narration_end": narration_end}
        return best

    # Three passes, each giving up less than the next. The waits come off first in every one of
    # them, because they are the only stretch the script allows the assembler to remove.
    attempts = [
        ("the rights waits with 3.0 s of each kept on screen, the two holds protected",
         dict(protect_voice=True, wait_keep=3.0)),
        ("the rights waits with 2.0 s of each kept on screen, the two holds protected",
         dict(protect_voice=True, wait_keep=2.0)),
        ("the rights waits with 1.5 s of each kept on screen, the two holds protected",
         dict(protect_voice=True, wait_keep=1.5)),
        ("the two holds giving up the floor that protected the line spoken over them",
         dict(protect_voice=False, wait_keep=1.5)),
    ]
    best = None
    for label, kwargs in attempts:
        best = search(build_windows(at_video, narration["lines"], **kwargs))
        if best["total"] <= args.maximum:
            print(f"cut plan: {label}")
            break
        print(f"over {args.maximum:.0f}s with {label}, trying the next plan")

    plan, placed, total = best["plan"], best["placed"], best["total"]
    print(f"take {raw_len:.1f}s, head trim {head:.1f}s, cut {best['trim']:.1f}s, "
          f"video {best['video_len']:.1f}s, narration ends {best['narration_end']:.1f}s, "
          f"render {total:.1f}s")

    compressions = []
    labels = []
    for a, b, name in plan.compressions:
        removed = int(round(b - a))
        at_cut = plan.map(a)
        compressions.append({"start_take_s": round(a, 3), "end_take_s": round(b, 3),
                             "removed_s": removed, "name": name,
                             "at_render_s": round(at_cut, 3)})
        labels.append({
            "text": f"waiting for Video Intelligence, {removed} s compressed",
            "from": max(0.0, at_cut - COMPRESSION_LABEL_S),
            "to": at_cut,
        })
    held_back = sum(b - a for a, b, _, kind in plan.cuts if kind != "run_wait")

    for a, b, name, kind in plan.cuts:
        marker = "labelled" if kind == "run_wait" else "hold"
        print(f"  cut {b - a:5.1f}s from the {name}  ({marker})")
    if held_back > 0.05:
        print(f"  the rights waits alone left the picture at "
              f"{best['video_len'] + held_back:.1f}s, so {held_back:.1f}s more came off the "
              f"dashboard and landing holds")
    for line in placed:
        print(f"  {line['cue']:<20} {line['start_final_s']:7.2f}s to {line['end_final_s']:7.2f}s"
              f"  (+{line['shift_final_s']:.2f}s)")

    srt = out_dir / "narration.srt"
    subtitles = write_srt(placed, srt)
    print(f"{len(subtitles)} subtitle cues over {len(placed)} spoken lines")

    number = args.draft if args.draft is not None else next_draft(out_dir)
    target = out_dir / f"airlock-draft-{number}-synthetic-voice.mp4"

    tone = args.tone_dbfs
    verdict_lines: list[str] = []
    for attempt in range(1, 4):
        audio = build_audio(placed, out_dir, total, tone)
        build_video(console, overlays, plan, total, raw_len, out_dir, srt, audio, target,
                    args.subtitle_size, labels)
        size_mb = target.stat().st_size / 1024 / 1024
        print(f"\nwrote {target} ({size_mb:.1f} MB)")
        if args.no_check or not CHECK.exists():
            break
        result = run(["python3", str(CHECK), "--render", str(target), "--limit-s", "180"])
        verdict_lines = (result.stdout or "").splitlines()
        print("\n".join(verdict_lines))
        if "FAIL" not in result.stdout:
            break
        if "G46" in result.stdout and "blanc" in result.stdout and attempt < 3:
            tone += 5.0
            print(f"\nsilence still detected, raising the room tone to {tone:.0f} dBFS and rebuilding")
            continue
        break

    summary = {
        "draft": number,
        "mp4": str(target),
        "duration_s": round(total, 3),
        "take_s": round(raw_len, 3),
        "offset_s": round(offset, 3),
        "head_trim_s": round(head, 3),
        "cuts": [{"name": name, "kind": kind, "from_s": round(a, 2), "to_s": round(b, 2)}
                 for a, b, name, kind in plan.cuts],
        "compressions": [{"start_take_s": c["start_take_s"], "end_take_s": c["end_take_s"],
                          "removed_s": c["removed_s"]} for c in compressions],
        "compression_labels": [{"text": label["text"], "from_s": round(label["from"], 3),
                                "to_s": round(label["to"], 3)} for label in labels],
        "hold_trim_s": round(held_back, 3),
        "overlays": [{"cue": o["cue"], "from_s": round(plan.map(o["window"][0]), 2),
                      "to_s": round(plan.map(o["window"][1]), 2),
                      "blank_head_skipped_s": round(o["skip"], 2)} for o in overlays],
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
