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
uv run --group video python video/narrate.py             # 0. the voice, before the take
node video/record.mjs                                    # 1. the take
uv run --group video python video/narrate.py             # 2. the narration on the take's cues
uv run python video/assemble.py                          # 3. the render and the check
```

The narration is synthesised twice and that is on purpose: the recorder holds the verdict card for
exactly as long as the line spoken over it, and it reads that length out of `narration.json`. Run 0
gives it a narration at the current speaking rate to measure; run 2 places the same lines on the
cues the take actually produced.

1. **`video/record.mjs`** (Playwright, chromium, headless) opens a 1920x1080 context with video
   recording on, drives the console through the beats of section 2 of the script, and writes
   `video/out/cues.json`: one `{cue, t}` per moment the script narrates, in seconds since the
   recording started. It reads the console v3 DOM and nothing else: an asset is picked by clicking
   its `button[aria-pressed]` card by name in the strip, a gate has landed when its
   `button[aria-controls="check-<gate>"]` row stops saying "Checking", the verdict and its motive
   are parsed out of the `p[aria-live="polite"]` summary of `section[aria-label="Verdict"]`, and
   the incident id out of the escalation row. The mute switch is reached by expanding the rights
   row and the Grafana href by switching the `Checks | Findings | Record` segmented control to
   Record and straight back, so the clip never leaves the screen; that detour is a second and a
   half of the Record segment on camera and the recorder reads the run's cost line out of it into
   `cue record_open`, so a draft that says $0 says so in the cue log too. On the Crest run the
   claim beat
   switches to Findings, clicks the first time chip of the claim finding so the clip seeks there,
   holds 3 s and goes back to Checks (`cue seek_claim`, then `cue seek_done` once it is back on
   Checks, which is where the assembler may start compressing again); the clip autoplays on the
   stage through every run and the recorder writes a note if it ever reports otherwise. The verdict
   card is held for the length of the line spoken over it, read out of `narration.json`, before the
   camera leaves for the dashboard. It logs each gate the moment its status line settles, so the four
   gates can land in any order. Every wait has a 200 s timeout and names the cue it gave up on,
   and the take stops there rather than recording a beat that never happened. Grafana is
   visited on a second page of the same context, because the console keeps a finished run in the
   page and navigating the recorded tab away would throw the verdict card out of the take;
   Playwright writes that page to its own file and step 3 lays it over the take. That file opens
   on a blank tab and then shows a dashboard drawing itself, and none of that belongs in the
   video, so the recorder logs `grafana_ready` and `dashboard_ready` the moment the panels have
   drawn their canvases, and writes the same instant into the overlay entry as `ready_at`. An
   insert holds still for two seconds, so the annotation the voice points at is read where it
   landed, and then glides down the panels for the rest of its window; the overlay entry says from
   when to when it was actually moving (`glide_from`, `glide_to`, `glide_px`), which is what the
   pace measurement in step 3 counts, and a dashboard that turns out not to be scrollable says so
   in the notes.

   Flags: `--url <url>`, `--mock` (the url is a local mock server: no telemetry wait, fixed
   verdicts), `--asa` (bring back the external ASA ruling page, dropped in script v5),
   `--skip-asa` (kept for compatibility, and now the default), `--prep`, `--gap-min <m>`,
   `--no-wait`, `--min-mute-age <s>`, `--headed`.

   `node video/measure_layout.mjs` is the one-off next to it: it opens the console at 1920x1080 and
   writes the bounding boxes of the verdict card, the check rows and the stage to
   `video/out/layout.json`, which is where the punch-in centres in `assemble.py` come from.

2. **`video/narrate.py`** reads the voice line of every beat of `docs/VIDEO-SCRIPT.md` (the part
   after the `|`) and places it on the cue that beat's own picture description names in
   parentheses, `(cue claim_done)`, the first one when it names two; a beat that names no cue, or
   one the take never reached, keeps the script's timecode and says so under `start_source`. The
   mapping is therefore by name and never positional, so a beat can be added to the script without
   renumbering anything here. It synthesises each line at 24 kHz LINEAR16, speaking rate 1.1, and
   trims the silence off both ends of every wav: about seven seconds over the whole script, and
   seven seconds of lines not being pushed off the picture they describe. It writes one wav per line into
   `video/out/voice/` and `video/out/narration.json`. Two lines never overlap: the second slides
   to the end of the first plus 0.4 s, and the shift is written down.

3. **`video/assemble.py`** converts the take to 1920x1080 at 30 fps constant H.264, lays each
   Grafana page over the take from its `ready_at` to the moment it closed, so an insert opens on a
   drawn dashboard and never on a loading one and the console take plays underneath until then (a
   page whose panels never drew falls back to skipping the black head blackdetect measures), burns
   the Article 50 overlay over the first 5 s
   and the subtitles from `narration.json`, mixes the narration at its cue times over a quiet room
   tone, normalises to -16 LUFS integrated with the true peak under -1 dBTP, plays a punch-in on
   every landing, and writes `video/out/airlock-draft-<n>-synthetic-voice.mp4`. It then
   runs the render gates and prints the verdict:

   ```bash
   python3 ~/Code/growth-cockpit/career/hackathon-evals/check.py --render <mp4> --limit-s 180
   ```

   The take is always longer than the video, so the assembler cuts, and the only thing it is
   allowed to take out is waiting. There are four kinds of it, and each one is a stretch where a
   line has been said and the console is holding until something answers: the rights gate waiting
   on Video Intelligence, from the moment the last of the other three chips settles to the moment
   rights settles; the seconds between two gates landing, after the line about the first one has
   been said; the seconds the verdict agent spends asking Grafana about each gate before the card
   fills; and a Grafana insert drawing its panels while the console take holds on a card that has
   already settled. Every stretch taken out says so on the picture, a mono caption at the top
   centre reading "waiting for Video Intelligence, N s compressed", "waiting for the claim gate,
   N s compressed", "waiting for the verdict agent, N s compressed" or "waiting for Grafana to
   draw, N s compressed" over the 2.5 s that run up to the cut, and every one of them is written
   into `assembly.json` under `compressions` with its kind. Half a second of every wait stays on
   the picture, which is what the caption is spoken over. The two smaller kinds only earn a cut
   when they take out four seconds or more, because a caption costs the picture more than three
   seconds of waiting does. The
   subtitles are one cue per sentence rather than one per spoken line, each sentence taking its
   share of that line's wav duration, wrapped at about 60 characters over two rows at most, while
   the narration audio stays one wav per line. The claim
   seek the recorder plays right after the claim gate lands is never inside a compressed stretch:
   that window starts at `seek_done`, because what gets compressed has to be waiting and nothing
   else. Every cue time is mapped through the cuts before the narration is placed, so a line
   still lands on the picture it describes.

   The cut aims at nothing. Every wait comes off whole and the render lands where it lands: past
   `--max` a hold is shortened, under `--min` whole waits go back on the picture shortest first
   (never one longer than six seconds, and never in part), and if it still lands short it lands
   short and prints that it did. Nothing is ever padded to reach a length. `check.py --limit-s 180`
   is the hard limit; script v5 asks for 150 to 170.

   Then the two measurements the pace direction is made of, both written into `assembly.json` and
   printed. **The punch-ins**: 1.15x over 1.2 s on every landing, eased in and out, towards the
   Checks column for a gate, the verdict summary for a verdict, the stage for the claim seek. The
   centres come from `video/measure_layout.mjs`; 1.15x can only move the frame 125 px across and
   70 px down before the crop would leave the picture, so most of them clamp, and `punches` carries
   both the centre asked for and the one reached. Two landings closer together than the move itself
   resolve rather than pile up, and `punches_dropped` says which and why. It is the only motion
   effect in the render: no transitions, no music. **The pace**: `pace` carries the longest stretch
   of the render with neither a change of picture nor a line playing, and where it starts. A change
   of picture is a cut, an insert opening or closing, a caption appearing, a punch-in, a cue of the
   take; a clip playing on the stage is deliberately not one, so a run's own dead seconds count in
   full.

   Flags: `--min`, `--max`, `--draft <n>`, `--subtitle-size`, `--tone-dbfs`, `--no-check`.

## What lands in `video/out/`

```
cues.json          the take: every cue with its time, the Grafana overlays with the instant
                   their panels drew and the window they were gliding, the notes
layout.json        where the console puts the verdict card, the check rows and the stage, which
                   is where the punch-in centres come from
prep.json          the two preparation runs, when they ran and what they returned
raw/console.webm   the console take, one file for the whole recording
raw/*.webm         one file per Grafana page the recorder opened
voice/NN-cue.wav   one synthetic line per beat
narration.json     each line with its cue, its wav, its duration and where it starts
narration.srt      the burned subtitles, in the render's own timeline
assembly.json      the cut plan and its compressions, the overlay windows, the punch-ins and
                   the ones dropped, the pace measurement, the final line and subtitle times,
                   the check verdict
airlock-draft-<n>-synthetic-voice.mp4
logs/              the recorder, the ffmpeg command and its output
```

## What a human still has to do

The render gates are mechanical. They do not read the picture. Watch the draft for the beats that
only a person can judge: whether a gate card is readable at the moment its line is spoken, whether
a punch-in lands on the thing that changed or on the frame next to it, whether a subtitle covers
something that matters, whether the cost line on the Record segment reads as a real number, and
whether the verdict the take produced is the verdict the script promises.
