# Demo day runbook (recording on or before 2026-09-03)

1. `scripts/demo_prep.sh`: assets hashed, every gate recalibrated (CAUGHT), hosted services
   answering, one timed Crest run. Run the timing twice more by hand
   (`uv run python scripts/query_agent_engine.py <engine> gs://.../real/CrestToothpa-18-48.mp4`);
   if any run is over 70 s, cut the 15 s excerpt (`ffmpeg -ss 33 -t 15 -c copy`), upload it, and
   point the console's `crest` asset at it (`console/src/lib/assets.ts`, redeploy).
2. In the console, switch "mute telemetry" on for the rights gate and run the clean clip once, at
   least 16 minutes before recording, so the "control unavailable" beat is real. Leave it muted.
3. Open the public dashboard in a second tab set to "Last 1 hour" so the annotation markers of the
   recording are visible when the script cuts to it at 2:38.
4. The take is recorded by `video/record.mjs` against the live console (see `video/README.md`);
   the drafts carry a synthetic voice. For the final with Dylan's voice: record the script's lines
   one wav per line in a quiet room, name them after the cues (`stake.wav`, `console_idle.wav`,
   `crest_click.wav`, ...), drop them in `video/out/voice-human/`, and run `narrate.py` with the
   human voice directory in place of the synthesis (the option is added when the lines exist);
   `assemble.py` then does the rest, subtitles included.
5. The render checker must PASS: `AIRLOCK_RENDER_CHECK=<path to check.py> uv run python video/assemble.py`
   runs it as `python3 $AIRLOCK_RENDER_CHECK --render <mp4> --limit-s 180` (see `video/README.md`;
   with the variable unset the assembler says "render check skipped, no checker configured").
6. Upload unlisted on YouTube with the English subtitles; tick the video box in `docs/DEVPOST.md`
   and rerun the same checker with `--type submission docs/DEVPOST.md`.

After recording: switch the mute off and run the clean clip once so the stack returns to a
healthy, calibrated state for the judges who try the URL.
