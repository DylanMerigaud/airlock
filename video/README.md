# video: the Airlock demo, built from the live console

Three commands turn `docs/VIDEO-SCRIPT.md` and the hosted reviewer console into a rendered video.
The picture is a real take: a script drives the live console at
https://airlock-console-771466810465.us-central1.run.app through the beats of the script and logs
the wall time each beat landed at, because a run takes between 30 and 110 s and no beat can sit on
a fixed clock. The narration is then laid on those cue times, not on the script's timecodes.

**The voice is synthetic**, generated with Google Cloud Text to Speech (project
`airlock-agentic-cinema`, voice `en-US-Neural2-D`, speaking rate 1.1), and every render says so
twice: in its file name (`airlock-draft-<n>-synthetic-voice.mp4` for the drafts,
`airlock-v6-synthetic-voice.mp4` for the final) and in a caption burned top right over the first
8 s and the last 6 s, worded from `narration.json` so it cannot name a voice the mix does not
carry. A human voice was the plan and the entrant had no recording time before the deadline
(decision of 2026-09-05, in the script header).

## Before recording (script v6: no preparation run)

Script v6 has no muted run and no staleness wait. The "control unavailable" beat is a fault the
reviewer injects on camera: the "Inject a fault" switch on the rights row makes the gate raise a
TimeoutError before it spends anything, the ERROR reaches Loki with the run id, and the verdict
blocks on it at once. So the recorder starts the take the moment the console is up. What still has
to be true before a take, read and not assumed:

```bash
gcloud run jobs executions list --job=airlock-daily-proof --region=us-central1 --limit=2
   # the morning's proof completed, so the PASS at the end rests on a calibration of today
gcloud storage ls gs://airlock-agentic-cinema-assets/synthetic/nimbus-test-clip-substantiated.mp4.substantiation.yaml
   # the study the fourth preset rests on is beside its asset in the bucket
curl -s https://airlock-console-771466810465.us-central1.run.app/api/health
   # the four gates answer, no error in the last 15 minutes (a fault run by someone else
   # inside that window changes the rights row's first picture and the third run's error ratio)
```

Run nothing else on Video Intelligence during the take (no calibration, no eval): the rights gate
of every run is already 30 to 90 s of that API. Other people may hit the hosted console meanwhile;
that cannot be helped, and the cue log says what the take actually got.

The recorder leaves the console as it found it: the fault switch is off again before the third
run, and the third run is a clean PASS on the fourth preset, so the stack is healthy for anyone who
opens the URL afterwards.

## The three commands, in order

```bash
uv run --group video python video/narrate.py             # 0. the voice, before the take
node video/record.mjs                                    # 1. the take
uv run --group video python video/narrate.py             # 2. the narration on the take's cues
uv run python video/assemble.py --output airlock-v6-synthetic-voice.mp4   # 3. the render and the check
```

The narration is synthesised twice and that is on purpose: the recorder holds the verdict card for
exactly as long as the line spoken over it, and it reads that length out of `narration.json`. Run 0
gives it a narration at the current speaking rate to measure; run 2 places the same lines on the
cues the take actually produced.

1. **`video/record.mjs`** (Playwright, chromium, headless) opens a 1920x1080 context with video
   recording on, drives the console through the beats of the script, and writes
   `video/out/cues.json`: one `{cue, t}` per moment the script narrates, in seconds since the
   recording started. It reads the console DOM and nothing else: an asset is picked by clicking
   its `button[aria-pressed]` card by name in the strip, a gate has landed when its
   `button[aria-controls="check-<gate>"]` row stops saying "Checking" ("Check failed" is an
   ERROR landing), the verdict and its motive are parsed out of the `p[aria-live="polite"]`
   summary of `section[aria-label="Verdict"]`, and the incident id out of the escalation row
   ("Incident N opened" or "Joined open incident N"). The "Inject a fault" switch is reached by
   expanding the rights row (`button[role="switch"]`, named by its text, beside "Mute telemetry").
   The three runs, in the order of the script:

   - the Crest commercial: the claim beat switches to Findings, clicks the first time chip of the
     claim finding so the clip seeks there, holds 3 s and goes back to Checks (`cue seek_claim`,
     then `cue seek_done` once it is back on Checks, which is where the assembler may start
     compressing again); the verdict card fills (`cue verdict`), the investigator and the
     escalation land under it (`cue escalation_done`, with the incident id), and the Record segment
     comes on camera for the last part of the verdict line (`cue record_open`): the recorder reads
     the cost line and the annotation and incident ids out of it into the cue log, so a take that
     says $0 says so there too, and takes the "Open in Grafana" href for the inserts;
   - the clean clip with the fault: the rights row is expanded, "Inject a fault" switched on
     (`cue fault_on`), the row closed, Run (`cue fault_click`); the rights row lands ERROR
     (`cue rights_error`, also `rights_done_2`), the three others land (`cue gates_done_2` on the
     last of them), the verdict blocks (`cue verdict_2`), the investigation row is expanded so its
     tool calls list on camera (`cue investigation`), the escalation lands (`cue
     escalation_done_2`); the Record shows the investigator's note and the Loki line it cites
     (`cue investigation_note`), a Grafana insert shows the public dashboard on its "Gate errors"
     panel for 4 s (`cue alert_insert`; the alert list itself needs a login the recorder's fresh
     browser does not have), then the reviewer signs as the platform on-call and clicks "Mark
     reviewed by a human" (`cue resolve`, then `cue resolved` with the incident's status and the
     reviewed annotation id);
   - the test clip with its study on file: the fault switched off first (`cue fault_off`; the
     console keeps the switch armed between runs), the fourth preset picked, Run (`cue
     study_click`), the four landings, the PASS (`cue verdict_3`), the dashboard insert (`cue
     dashboard`), the landing on the PASS card.

   The clip autoplays on the stage through every run and the recorder writes a note if it ever
   reports otherwise. Every hold is the length of the line spoken over it, read out of
   `narration.json` (the console idle until the stake and console lines are said, the verdict card
   for the verdict line, the resolved incident for the resolve line, the PASS card for the rights
   line), which is why the narration is synthesised once before the take and once after it. It
   logs each gate the moment its status line settles, so the four gates can land in any order.
   Every wait has a 200 s timeout and names the cue it gave up on, and the take stops there rather
   than recording a beat that never happened. Every cue name the recorder can write is in its
   `CUE_NAMES` array; `cue()` refuses any other, and `narrate.py` checks the script against that
   array before synthesising anything (`tests/test_video_cues.py` does the same in the suite).
   Grafana is visited on a second page of the same context, because the console keeps a finished
   run in the page and navigating the recorded tab away would throw the verdict card out of the
   take; Playwright writes that page to its own file and step 3 lays it over the take. That file
   opens on a blank tab and then shows a dashboard drawing itself, and none of that belongs in the
   video, so the recorder logs `alert_ready` and `dashboard_ready` the moment the panels have
   drawn their canvases, and writes the same instant into the overlay entry as `ready_at`. An
   insert holds still for two seconds, so the annotation the voice points at is read where it
   landed, and then glides down the panels for the rest of its window; the overlay entry says from
   when to when it was actually moving (`glide_from`, `glide_to`, `glide_px`), which is what the
   pace measurement in step 3 counts, and a dashboard that turns out not to be scrollable says so
   in the notes.

   Flags: `--url <url>`, `--mock` (the url is a local mock server, `AIRLOCK_MOCK=1 pnpm dev` in
   `console/`: fixed verdicts, no expectation notes), `--dashboard <url>`, `--out <dir>`,
   `--headed`. The v5 flags (`--prep`, `--gap-min`, `--no-wait`, `--min-mute-age`, `--asa`,
   `--skip-asa`) are gone with the muted run they served.

   `node video/measure_layout.mjs` is the one-off next to it: it opens the console at 1920x1080 and
   writes the bounding boxes of the verdict card, the check rows and the stage to
   `video/out/layout.json`, which is where the punch-in centres in `assemble.py` come from.

2. **`video/narrate.py`** reads the voice line of every beat of `docs/VIDEO-SCRIPT.md` (the part
   after the `|`) and places it on the cue that beat's own picture description names in
   parentheses, `(cue claim_done)`, the first one when it names two; a beat that names no cue, or
   one the take never reached, keeps the script's timecode and says so under `start_source`. The
   mapping is therefore by name and never positional, so a beat can be added to the script without
   renumbering anything here. Before it synthesises anything it checks every cue the script names
   against the recorder's `CUE_NAMES` and exits on a name the recorder never writes. It synthesises each line at 24 kHz LINEAR16, speaking rate 1.1, and
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
   every landing, burns the synthetic voice caption over the open and the landing, and writes
   `video/out/airlock-draft-<n>-synthetic-voice.mp4` (or the name given with `--output`). It then
   runs the render checker named by `AIRLOCK_RENDER_CHECK`, when one is configured, and prints
   its verdict:

   ```bash
   AIRLOCK_RENDER_CHECK=/path/to/check.py uv run python video/assemble.py
   # runs: python3 $AIRLOCK_RENDER_CHECK --render <mp4> --limit-s 180
   ```

   The checker is any script that takes `--render <mp4> --limit-s <s>` and prints PASS or FAIL
   (the "PASS mecanique" blocks in `docs/RUNS.md` came from one kept outside this repository).
   With the variable unset the step prints `render check skipped, no checker configured` and the
   assembler exits 0 with the render written; `--no-check` skips it explicitly.

   The take is always longer than the video, so the assembler cuts, and the only thing it is
   allowed to take out is waiting. There are five kinds of it, and each one is a stretch where a
   line has been said and the console is holding until something answers: the rights gate waiting
   on Video Intelligence, from the moment the line about the last of the other three landings has
   been said to the moment rights settles; the seconds between two gates landing, after the line
   about the first one has been said; the seconds the verdict agent spends asking Grafana about
   each gate before the card fills; the seconds the investigator spends reading Loki after the
   verdict line has been said and before the escalation lands (the first two runs only: the third
   run's investigator works under the dashboard insert, which is not waiting); and a Grafana
   insert drawing its panels while the console take holds on a card that has already settled.
   Every stretch taken out says so on the picture, a mono caption at the top centre reading
   "waiting for Video Intelligence, N s compressed", "waiting for the claim gate, N s compressed",
   "waiting for the verdict agent, N s compressed", "waiting for the investigator, N s compressed"
   or "waiting for Grafana to draw, N s compressed" over the 2.5 s that run up to the cut, and
   every one of them is written into `assembly.json` under `compressions` with its kind. Half a
   second of every wait stays on the picture, which is what the caption is spoken over. The three
   smaller kinds only earn a cut when they take out four seconds or more, because a caption costs
   the picture more than three seconds of waiting does. The
   subtitles are one cue per sentence rather than one per spoken line, each sentence taking its
   share of that line's wav duration, wrapped at about 60 characters over two rows at most, while
   the narration audio stays one wav per line. The claim
   seek the recorder plays right after the claim gate lands is never inside a compressed stretch:
   that window starts at `seek_done`, because what gets compressed has to be waiting and nothing
   else. Every cue time is mapped through the cuts before the narration is placed, so a line
   still lands on the picture it describes.

   The cut aims at nothing. Every wait comes off whole and the render lands where it lands: past
   `--max` a hold is shortened; under `--min`, or while the voice outlasts the picture (the last
   frame would be cloned to cover the difference, and the assembler prints by how much), whole
   waits go back on the picture shortest first (never one longer than six seconds, and never in
   part), and if it still lands short it lands short and prints that it did. Nothing is ever
   padded to reach a length. The checker's `--limit-s 180` is the hard limit; script v6 asks for
   150 to 175.

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
raw/console.webm   the console take, one file for the whole recording
raw/*.webm         one file per Grafana page the recorder opened
voice/NN-cue.wav   one synthetic line per beat
narration.json     each line with its cue, its wav, its duration and where it starts
narration.srt      the burned subtitles, in the render's own timeline
assembly.json      the cut plan and its compressions, the overlay windows, the punch-ins and
                   the ones dropped, the pace measurement, the final line and subtitle times,
                   the check verdict
airlock-v6-synthetic-voice.mp4      the final (airlock-draft-<n>-synthetic-voice.mp4 for a draft)
logs/              the recorder, the ffmpeg command and its output
```

## What a human still has to do

The render gates are mechanical. They do not read the picture. Watch the draft for the beats that
only a person can judge: whether a gate card is readable at the moment its line is spoken, whether
a punch-in lands on the thing that changed or on the frame next to it, whether a subtitle covers
something that matters, whether the cost line on the Record segment reads as a real number, and
whether the verdict the take produced is the verdict the script promises.
