# Demo day runbook (the final take was recorded on 2026-09-05, script v6)

1. Before the take, read and do not assume: the morning's daily proof completed
   (`gcloud run jobs executions list --job=airlock-daily-proof --region=us-central1 --limit=2`),
   the substantiation file is beside the fourth preset's asset
   (`gcloud storage ls gs://airlock-agentic-cinema-assets/synthetic/nimbus-test-clip-substantiated.mp4.substantiation.yaml`),
   and `/api/health` on the console answers with the four gates calibrated and no error in the last
   15 minutes. Run nothing else on Video Intelligence during the take (no calibration, no eval).
2. No preparation run. Script v6 has no muted gate and no staleness wait: the control beat is the
   "Inject a fault" switch on the rights row, thrown on camera by the recorder, and the gate fails
   in a millisecond. The recorder switches it off again before the third run.
3. The take is recorded by `video/record.mjs` against the live console (see `video/README.md`),
   then narrated and assembled:

   ```bash
   uv run --group video python video/narrate.py                              # the line lengths the recorder holds for
   node video/record.mjs                                                     # the take, one go, about 5 minutes of pipeline time
   uv run --group video python video/narrate.py                              # the lines on the take's cues
   AIRLOCK_RENDER_CHECK=<path to check.py> uv run python video/assemble.py --output airlock-v6-synthetic-voice.mp4 --max 176
   ```

   If a cue times out, the recorder says which one and stops; fix and retake, three takes at most.
4. The voice is synthetic (Google Cloud Text to Speech, en-US-Neural2-D at 1.1), declared in the
   file name, in a caption over the open and the landing, and in the YouTube description. A human
   voice was the plan; there was no recording time before the deadline (decision of 2026-09-05).
5. The render checker must PASS: the assembler runs it as
   `python3 $AIRLOCK_RENDER_CHECK --render <mp4> --limit-s 180` (with the variable unset it says
   "render check skipped, no checker configured"). Then look at the frames at the landings and the
   inserts, and read the pace line the assembler prints (the longest stretch with no change of
   picture and no voice).
6. Upload unlisted on YouTube with the English subtitles (`video/out/narration.srt`) and the
   synthetic voice named in the description; tick the video box in `docs/DEVPOST.md` and rerun the
   same checker with `--type submission docs/DEVPOST.md`.

After the take the stack is left healthy: the third run is a clean PASS with the fault off, so the
judges who try the URL find four healthy, calibrated gates.
