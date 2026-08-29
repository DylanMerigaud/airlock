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
4. Record one take of the console at 1920x1080, 30 fps, following `docs/VIDEO-SCRIPT.md`. The
   voice is recorded separately and laid over the take; subtitles burned in from the script.
5. `python3 <cockpit>/career/hackathon-evals/check.py --render demo.mp4 --limit-s 180` must PASS.
6. Upload unlisted on YouTube with the English subtitles; tick the video box in `docs/DEVPOST.md`
   and rerun `check.py --type submission docs/DEVPOST.md`.

After recording: switch the mute off and run the clean clip once so the stack returns to a
healthy, calibrated state for the judges who try the URL.
