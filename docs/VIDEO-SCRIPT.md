# Video script: Airlock for Agentic Cinema

Espece: demo (the sponsors sell infrastructure, Google Cloud and Grafana, so a screencast of the software at 30 fps; the artefact is the proof that it runs)
Duree cible: 180s
Voix: off humaine (Dylan, recorded separately from the screen, read from this script, re-recorded if one word is off)
Musique: aucune

One take inside the console, no cut inside a run, the trace as the interface. The stake, the stack
and the practitioner quotes go inside the product frame, never on a slide. Timings below assume
the Crest excerpt run completes in 70 s or less (see the checklist); if it measures longer on the
recording day, the 15 s excerpt replaces it.

## 1. The situation that hurts

[0:00] The console, idle, dark. Over it, the first lines of Article 50 of the EU AI Act (in force 2026-08-02) as a text overlay, then it fades to the console's headline. | "Since August 2026 the law requires generated content to be marked in a machine-readable way. Studios ship dozens of generated assets a week. Nobody signs each one by hand fast enough, and nobody can prove which one was checked, by which rule, or whether the check was working."
[0:08] A browser tab with a real ASA ruling (Nutri-Paw, 26 August 2026) and a CARA bulletin side by side, the cursor scrolling the ruling's assessment. | "This is the reviewer's job today: a ruling on one side, the asset on the other, and no trace of what was checked."
[0:18] Back to the console: the asset picker, two preloaded assets, the Run button. | "Airlock is the airlock between the generator and the broadcast. Four gates, then a verdict that has to ask Grafana before it rules."

## 2. The system acting

[0:25] Pick the Crest commercial (Prelinger Archives, 1960s, public domain, 30 s excerpt). Click Run airlock. The five gate cards turn to RUNNING with the step named: "Video Intelligence: logos, faces, text", "gemini-2.5-pro reading claims", "gemini-2.5-flash against the charter", "C2PA manifest". | "A real commercial, a real trademark on screen. The four gates run in parallel on Vertex AI Agent Engine."
[0:32] The provenance row lands first: BLOCK, no C2PA manifest. The timeline row expands to the raw c2pa answer. | "Provenance is a cryptographic check, not an opinion: this film was shot decades before C2PA existed, and the gate says so."
[0:45] The brand row lands: BLOCK, the charter exclusions quoted with timestamps. The claim row lands: BLOCK, "21 percent fewer cavities" and "more dentists recommend" cited under 16 CFR 255.2 and 255.3, the ASA reference beside them. | "The claim gate reads every claim with its timestamp and maps it to the rule: a consumer testimonial, an expert endorsement, an organisation endorsement, none of them with substantiation on file."
[1:05] The rights row lands: BLOCK, the Crest logo at 16 s with its confidence, seven faces with no release. | "Rights: the Video Intelligence API found the logo and the faces; the registry clears neither."
[1:12] The verdict card fills: the four Grafana lines per gate (error rate, last success, calibration catches), then BLOCK, motive content, needs a human. The escalation row shows the incident id. The "open in Grafana" link is clicked: the public dashboard, the annotation marker just landed. | "Before it rules, the verdict asks Grafana about each gate: is it healthy, has it caught a real injected defect this week. Then it writes the verdict back as an annotation and opens the incident for the human."
[1:40] Pick the Nimbus test clip, caption "synthetic test asset, Veo 3.1 on Vertex AI, C2PA signed". Run. | "Second asset, generated, labelled, and signed with a real C2PA manifest."
[1:48] Provenance PASS in under a second, trusted signer named. Brand PASS. Claim BLOCK on "Recommended by 9 out of 10 sommeliers", 16 CFR 255.3. Rights PASS. | "Provenance and rights pass, the brand charter passes, and the claim gate blocks the one line we planted: an expert endorsement with nothing behind it."
[2:20] The mute toggle on the rights gate is switched on, Run again on the same clip. The rights card turns amber; the verdict says BLOCK, control unavailable, last success older than 900 seconds. | "Now disable the rights gate's telemetry and run again. The gate still says PASS. Grafana cannot see it succeed, so the verdict refuses. A control nobody can see is not a control."

## 3. The result, in numbers

[2:38] The public Grafana dashboard: the verdict tiles (blocks by motive, one PASS), calibration catches and misses per gate, seconds since last success, the annotation markers on the run panel. | "Every verdict of the day is an annotation on this dashboard. Every needs-human block is an incident. Each gate had to catch a real injected defect before it earned the right to block."
[2:50] Ten-second overlay inside the console frame: two practitioner quotes attributed by role (or the overlay is cut if none by 2026-09-05). | (silence under the quotes)
[2:58] The verdict card of the clean signed clip: PASS, all four gates healthy and calibrated. Hold. | "Nothing ships without a gate that has already caught a real defect. That is Airlock."

## Checklist de rendu

- [ ] The Crest excerpt run measured three times alone on the recording day; if any run is over 70 s, cut and use the 15 s excerpt (seconds 33 to 48 of the original) and re-measure
- [ ] Rights telemetry muted at least 16 minutes before the recording so the "control unavailable" run is real
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
