# Video script: Airlock for Agentic Cinema

Espece: demo (the sponsors sell infrastructure, Google Cloud and Grafana, so a screencast of the software at 30 fps; the artefact is the proof that it runs)
Duree cible: 180s
Voix: off humaine (Dylan, recorded separately from the screen, read from this script, re-recorded if one word is off; the iteration drafts use a synthetic voice from Google Cloud Text-to-Speech and say so in their file name)
Musique: aucune

Cut for pace, the winners' length without a slack second: no stretch longer than 2 s without a
change of picture or a voice; a punch-in (1.15x over 1.2 s) on every landing (the gate row that
lands, the verdict summary, the seek); the voice at 1.1x; the target is 150 to 170 s.
One take inside the console, the clip on the stage while the gates read it. The rights gate waits
30 to 70 s on the Video Intelligence API in every run, and a Grafana insert takes a few seconds to
draw its panels; the cut keeps one second of each of those waits, then compresses the rest and says
so on screen ("waiting for Video Intelligence, N s compressed", "waiting for Grafana to draw, N s
compressed"), never hiding it and cutting nothing that is not waiting. No stretch without a voice
longer than 6 s: a line lands on every gate landing. Each picture line names its cue in parentheses so the narration is placed where
the picture is (the cue ids are the recorder's, `video/record.mjs`). Three runs, one
decision shown three ways: the real film blocked on its content, a clean asset blocked because a
control went dark, the same asset passed once the control is back. The stake, the stack and the
practitioner quotes go inside the product frame, never on a slide. The rights gate's telemetry is
muted at least 16 minutes before the take starts (docs/DEMO-DAY.md), so Grafana's view of it is
stale when the take begins; it is switched back on at 2:10, on camera.

## 1. The situation that hurts

[0:00] The console, idle. Over it, one line of Article 50 of the EU AI Act (in force 2026-08-02) as a text overlay for 5 s, then the console alone (cue stake). | "Since August 2026 the law wants generated content marked. Studios ship dozens of generated assets a week; the reviewer checks by hand, and nobody can prove which one was checked."
[0:06] The console: the Crest clip on the stage, the three assets under it, the gate rows with their calibration lines read from Grafana; the rights row is amber, "last success 17 min ago" (cue console_idle). | "Airlock: four gates, then a verdict that asks Grafana before it rules. The rights gate is amber: its telemetry has been dark for seventeen minutes. Remember that."

## 2. The system acting

[0:12] Click Run airlock on the Crest commercial (Prelinger Archives, 1960s, public domain, 30 s excerpt). The clip plays on the stage; the gate rows turn to RUNNING with the step named (cue crest_click). | "A real commercial with a real trademark on screen. The four gates run in parallel on Vertex AI Agent Engine while the clip plays."
[0:16] Provenance lands first: BLOCK, no C2PA manifest (cue provenance_done). | "Provenance is a cryptographic check, not an opinion: this film was shot decades before C2PA existed."
[0:22] Brand lands: BLOCK, the charter exclusions quoted with timestamps (cue brand_done). | "Brand: the charter forbids health claims, comparisons and children, and the wordmark is not even there."
[0:29] Claim lands: BLOCK; a time chip of the claim finding is clicked at once and the clip seeks to the claim (cue claim_done). | "Click the time and the clip goes there. The claim gate reads every claim with its timestamp and maps it to the rule: an expert endorsement, an organisation endorsement, no substantiation on file."
[0:38] Rights lands: BLOCK, the Crest logo with its confidence, the faces with no release (cue rights_done). | "Rights: the Video Intelligence API found the logo and the faces; the registry clears neither."
[0:44] The verdict summary fills: BLOCK, content, needs a human, a punch-in on it; the escalation row shows the incident id; the card is held for the whole line (cue verdict). | "Before it rules, the verdict asks Grafana about each gate: healthy, and has it caught a real injected defect this week. Then it writes the verdict back as an annotation and opens the incident for a human."
[0:56] The public dashboard for 5 s, the annotation that just landed on the run panel (cue grafana_open). | "There it is, on the dashboard."
[1:02] Pick the Nimbus clean clip, caption "synthetic test asset, Veo 3.1 on Vertex AI, C2PA signed". Run; the clip plays (cue clean_muted_click). | "A clean generated asset, signed with a real manifest."
[1:06] Provenance lands PASS, the trusted signer named (cue provenance_done_2). | "Provenance passes in under a second: the manifest verifies against the studio's own trust list. Brand and claim follow."
[1:20] Rights lands PASS after its wait (cue rights_done_2). | "Four gates pass."
[1:23] The verdict: BLOCK, motive control unavailable, "rights: last success older than 900 seconds" (cue verdict_2). | "And the verdict still refuses: Grafana cannot see the rights control succeed, so its PASS does not count. A control nobody can see is not a control."
[1:36] Switch the rights gate's "mute telemetry" off. Run the same clip again (cue unmute, cue clean_click_2). | "Turn the telemetry back on and run again."
[1:41] Provenance lands PASS again (cue provenance_done_3). | "Same clip, same gates."
[1:48] Brand and claim land PASS; the rights row shows "Checking: Video Intelligence" with its calibration line (cue claim_done_3). | "Brand and claim pass again. The rights gate reads the clip one more time, and this time its push reaches Grafana."
[2:05] The verdict card: PASS, "all 4 gates PASS, healthy and calibrated", the annotation id (cue verdict_3). | "Now every gate is healthy and has caught a real injected defect this week. This is the PASS the reviewer no longer signs by hand."

## 3. The result, in numbers

[2:18] The public Grafana dashboard: the verdict tiles, calibration catches and misses per gate, seconds since last success, the annotation markers of the three runs (cue dashboard). | "Every verdict is an annotation on this dashboard. Every block that needs a human is an incident. Each gate had to catch a real injected defect before it earned the right to block."
[2:30] The PASS verdict card, held (cue landing). | "Nothing ships without a gate that has already caught a real defect. That is Airlock."

## Checklist de rendu

- [ ] The Crest run measured three times alone on the recording day; the rights gate costs 30 to 45 s whatever the input length (measured 2026-08-29), so each run is 45 to 75 s and the take is re-timed from the draft's cue log, not from this script's targets
- [ ] Rights telemetry muted at least 16 minutes before the take (one muted run of the clean clip, then nothing unmuted)
- [ ] Calibration ledger run within the day (`python -m airlock.calibrate`), every gate CAUGHT, so the PASS at the end is earned
- [ ] The synthetic clip regenerated only if a visible artefact appears (none on 2026-08-28)
- [ ] 1920x1080, 30 fps constant, 170 to 190 s, `check.py --render demo.mp4 --limit-s 180` PASS
- [ ] Voice at -16 LUFS, true peak under -1 dBTP, no silence over 4 s, no black over 1.5 s at the open
- [ ] Subtitles burned in from this script; the voice re-recorded if one word is off
- [ ] Product on screen at least 150 s of 180, zero slides, no face before 2:50 if at all
- [ ] The stack named on screen as it runs (the spec strip and the gate cards), the models named in the voice
- [ ] No dock, no taskbar, no notification, fewer than 8 tabs, no video player chrome, no spinner without a label
- [ ] No dash in any on-screen text (console copy and overlays swept)
- [ ] Unlisted YouTube upload with English subtitles, the link plays on a cold device
