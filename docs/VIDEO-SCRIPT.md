# Video script: Airlock for Agentic Cinema

Espece: demo (the sponsors sell infrastructure, Google Cloud and Grafana, so a screencast of the software at 30 fps; the artefact is the proof that it runs)
Duree cible: 180s
Voix: off humaine (Dylan, recorded separately from the screen, read from this script, re-recorded if one word is off; the iteration drafts use a synthetic voice from Google Cloud Text-to-Speech and say so in their file name)
Musique: aucune

One take inside the console, no cut inside a run, the trace as the interface. Three runs, one
decision shown three ways: the real film blocked on its content, a clean asset blocked because a
control went dark, the same asset passed once the control is back. The stake, the stack and the
practitioner quotes go inside the product frame, never on a slide. The rights gate's telemetry is
muted at least 16 minutes before the take starts (docs/DEMO-DAY.md), so Grafana's view of it is
stale when the take begins; it is switched back on at 2:10, on camera.

## 1. The situation that hurts

[0:00] The console, idle, dark. Over it, the first lines of Article 50 of the EU AI Act (in force 2026-08-02) as a text overlay, fading to the console. | "Since August 2026 the law requires generated content to be marked in a machine-readable way. Studios ship dozens of generated assets a week. Nobody signs each one by hand fast enough, and nobody can prove which one was checked, by which rule, or whether the check was working."
[0:08] A browser tab with a real ASA ruling (Nutri-Paw, 26 August 2026), the cursor scrolling the assessment. | "This is the reviewer's job today: a ruling on one side, the asset on the other, and no trace of what was checked."
[0:17] Back to the console: three assets in the picker, the gate cards with their calibration lines read from Grafana; the rights card is amber, "last success 17 min ago". | "Airlock is the airlock between the generator and the broadcast: four gates, then a verdict that has to ask Grafana before it rules. Look at the rights gate: its telemetry has been dark for seventeen minutes. Keep that in mind."

## 2. The system acting

[0:25] Pick the Crest commercial (Prelinger Archives, 1960s, public domain, 30 s excerpt). Click Run airlock. The gate cards turn to RUNNING with the step named: "Video Intelligence: logos, faces, text", "gemini-2.5-pro reading claims", "gemini-2.5-flash against the charter", "C2PA manifest". | "A real commercial with a real trademark on screen. The four gates run in parallel on Vertex AI Agent Engine."
[0:30] Provenance lands first: BLOCK, no C2PA manifest. | "Provenance is a cryptographic check, not an opinion: this film was shot decades before C2PA existed."
[0:40] Brand lands: BLOCK, the charter exclusions quoted. Claim lands: BLOCK, "more dentists recommend" under 16 CFR 255.3, the American Dental Association seal under 255.4, the ASA reference beside them. | "The claim gate reads every claim with its timestamp and maps it to the rule: an expert endorsement, an organisation endorsement, no substantiation on file."
[0:55] Rights lands: BLOCK, the Crest logo with its confidence, the faces with no release. | "Rights: the Video Intelligence API found the logo and the faces; the registry clears neither."
[1:00] The verdict card fills: four Grafana lines, then BLOCK, motive content, needs a human; the escalation row shows the incident id. Click "open in Grafana": the public dashboard with the annotation that just landed. Back to the console. | "Before it rules, the verdict asks Grafana about each gate: healthy, and has it caught a real injected defect this week. Then it writes the verdict back as an annotation and opens the incident for a human."
[1:20] Pick the Nimbus clean clip, caption "synthetic test asset, Veo 3.1 on Vertex AI, C2PA signed". Run. All four gates land PASS, provenance naming the trusted signer. The verdict: BLOCK, motive control unavailable, "rights: last success older than 900 seconds". | "A clean generated asset, signed with a real manifest. Four gates pass. And the verdict still refuses: Grafana cannot see the rights control succeed, so its PASS does not count. A control nobody can see is not a control."
[2:08] Switch the rights gate's "mute telemetry" off. Run the same clip again. | "Turn the telemetry back on and run again."
[2:15] The gates land PASS again; the verdict card: PASS, "all 4 gates PASS, healthy and calibrated", the annotation id. | "Now every gate is healthy and has caught a real injected defect this week. This is the PASS the reviewer no longer signs by hand."

## 3. The result, in numbers

[2:40] The public Grafana dashboard: the verdict tiles, calibration catches and misses per gate, seconds since last success, the annotation markers of the three runs. | "Every verdict is an annotation on this dashboard. Every block that needs a human is an incident. Each gate had to catch a real injected defect before it earned the right to block."
[2:50] Ten-second overlay inside the console frame: two practitioner quotes attributed by role (cut if none by 2026-09-05). | (silence under the quotes)
[2:58] The PASS verdict card, held. | "Nothing ships without a gate that has already caught a real defect. That is Airlock."

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
