# video: the draft of the Airlock demo, built from the live console

Three commands turn `docs/VIDEO-SCRIPT.md` and the hosted reviewer console into a rendered draft.
The picture is a real take: a script drives the live console at
https://airlock-console-771466810465.us-central1.run.app through the beats of the script and logs
the wall time each beat landed at, because a run takes between 30 and 110 s and no beat can sit on
a fixed clock. The narration is then laid on those cue times, not on the script's timecodes.

**The voice in every file named `airlock-draft-<n>-synthetic-voice.mp4` is synthetic**, generated
with Google Cloud Text to Speech (project `airlock-agentic-cinema`, voice `en-US-Neural2-D`).
The final video's voice is Dylan's, recorded
separately from the same script and laid over the same take. The file name says which one you are
listening to; nothing else in the pipeline changes between the two.

## Preparation, before any recording

The "control unavailable" beat is only true if the rights gate's telemetry really is dark, so the
preparation is part of the take:

```bash
scripts/demo_prep.sh                 # assets hashed, every gate recalibrated, services answering
node video/record.mjs --prep         # two clean runs through the API, the second with rights muted
```

`--prep` uses no browser: it posts the clean clip to `/api/run` once with nothing muted, so every
gate gets a fresh success, then again 13 minutes later with `mute: ["rights"]`, so only the rights
control goes quiet. `record.mjs` then polls `/api/health` and starts the take once
`seconds_since_success` for the rights gate is past 990, which is the one window where the rights
row reads "17 min ago" and the other three are still healthy. The recorder switches the mute on
again itself at the start of the take (the console keeps that switch in the page, so a fresh
browser starts with it off) and switches it off on camera at the "turn the telemetry back on"
beat.

After the recording, switch the mute off and run the clean clip once so the stack is healthy for
anyone who opens the URL.

## The three commands, in order

```bash
node video/record.mjs                                    # 1. the take
uv run --group video python video/narrate.py             # 2. the synthetic narration
uv run python video/assemble.py                          # 3. the render and the check
```

1. **`video/record.mjs`** (Playwright, chromium, headless) opens a 1920x1080 context with video
   recording on, drives the console through the beats of section 2 of the script, and writes
   `video/out/cues.json`: one `{cue, t}` per moment the script narrates, in seconds since the
   recording started. It reads the console v3 DOM and nothing else: an asset is picked by clicking
   its `button[aria-pressed]` card by name in the strip, a gate has landed when its
   `button[aria-controls="check-<gate>"]` row stops saying "Checking", the verdict and its motive
   are parsed out of the `p[aria-live="polite"]` summary of `section[aria-label="Verdict"]`, and
   the incident id out of the escalation row. The mute switch is reached by expanding the rights
   row and the Grafana href by switching the `Checks | Findings | Record` segmented control to
   Record and straight back, so the clip never leaves the screen. On the Crest run the claim beat
   switches to Findings, clicks the first time chip of the claim finding so the clip seeks there,
   holds 3 s and goes back to Checks (`cue seek_claim`); the clip autoplays on the stage through
   every run and the recorder writes a note if it ever reports otherwise. The ASA ruling is
   scrolled slowly for 6 s on the wall clock, so that beat lasts exactly as long as it is worth
   and never has to be cut. It logs each gate the moment its status line settles, so the four
   gates can land in any order. Every wait has a 200 s timeout and names the cue it gave up on,
   and the take stops there rather than recording a beat that never happened. Grafana is
   visited on a second page of the same context, because the console keeps a finished run in the
   page and navigating the recorded tab away would throw the verdict card out of the take;
   Playwright writes that page to its own file and step 3 lays it over the take.

   Flags: `--url <url>`, `--mock` (the url is a local mock server: no telemetry wait, fixed
   verdicts), `--skip-asa` (skip the external ASA ruling page), `--prep`, `--gap-min <m>`,
   `--no-wait`, `--min-mute-age <s>`, `--headed`.

2. **`video/narrate.py`** reads the voice line of every beat of `docs/VIDEO-SCRIPT.md` (the part
   after the `|`) and places it on the cue that beat's own picture description names in
   parentheses, `(cue claim_done)`, the first one when it names two; a beat that names no cue, or
   one the take never reached, keeps the script's timecode and says so under `start_source`. The
   mapping is therefore by name and never positional, so a beat can be added to the script without
   renumbering anything here. It synthesises each line at 24 kHz LINEAR16, speaking rate 1.0. It writes one wav per line into
   `video/out/voice/` and `video/out/narration.json`. Two lines never overlap: the second slides
   to the end of the first plus 0.4 s, and the shift is written down.

3. **`video/assemble.py`** converts the take to 1920x1080 at 30 fps constant H.264, lays the
   Grafana pages over the windows they were open, minus the blank tab at the head of each one
   (the page is recorded from the moment it opens, so its first seconds are black and the console
   take plays through them instead), burns the Article 50 overlay over the first 8 s
   and the subtitles from `narration.json`, mixes the narration at its cue times over a quiet room
   tone, normalises to -16 LUFS integrated with the true peak under -1 dBTP, brings the total
   between 170 and 190 s, and writes `video/out/airlock-draft-<n>-synthetic-voice.mp4`. It then
   runs the render gates and prints the verdict:

   ```bash
   python3 ~/Code/growth-cockpit/career/hackathon-evals/check.py --render <mp4> --limit-s 180
   ```

   The take is always longer than the video, so the assembler cuts, and the only stretch it is
   allowed to take is the wait on the rights gate: from the moment the last of the other three
   chips settles to the moment rights settles, which is the Video Intelligence call and nothing
   else. Every stretch taken out of a run says so on the picture, a mono caption at the top
   centre reading "waiting for Video Intelligence, N s compressed" over the 2.5 s that run up to
   the cut, and every one of them is written into `assembly.json` under `compressions`. The
   subtitles are one cue per sentence rather than one per spoken line, each sentence taking its
   share of that line's wav duration, wrapped at about 60 characters over two rows at most, while
   the narration audio stays one wav per line. If the waits still leave the render over 179 s, the
   assembler keeps one second of each of them on screen, the number the picture itself promises,
   and shortens the dashboard hold and the landing hold instead, printing by how much. The claim
   seek the recorder plays right after the claim gate lands is never inside a compressed stretch:
   that window starts after the beat, because what gets compressed has to be waiting and nothing
   else. Every cue time is mapped through the cuts before the narration is placed, so a line
   still lands on the picture it describes. `check.py --limit-s 180` fails above 180 s, so the
   render targets 177 s and never goes over 179. Flags: `--target`, `--min`, `--max`,
   `--draft <n>`, `--subtitle-size`, `--tone-dbfs`, `--no-check`.

## What lands in `video/out/`

```
cues.json          the take: every cue with its time, the Grafana overlays, the notes
prep.json          the two preparation runs, when they ran and what they returned
raw/console.webm   the console take, one file for the whole recording
raw/*.webm         one file per Grafana page the recorder opened
voice/NN-cue.wav   one synthetic line per beat
narration.json     each line with its cue, its wav, its duration and where it starts
narration.srt      the burned subtitles, in the render's own timeline
assembly.json      the cut plan and its compressions, the overlay windows, the final line and
                   subtitle times, the check verdict
airlock-draft-<n>-synthetic-voice.mp4
logs/              the recorder, the ffmpeg command and its output
```

## What a human still has to do

The render gates are mechanical. They do not read the picture. Watch the draft for the beats that
only a person can judge: whether the ASA scroll shows the assessment, whether a gate card is
readable at the moment its line is spoken, whether a subtitle covers something that matters, and
whether the verdict the take produced is the verdict the script promises.
