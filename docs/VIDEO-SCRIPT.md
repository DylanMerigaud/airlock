# Video script: Airlock for Agentic Cinema

Kind: demo (the sponsors sell infrastructure, Google Cloud and Grafana, so a screencast of the software at 30 fps; the artefact is the proof that it runs)
Target length: 150 to 175 s (the rule is 3 minutes at most)
Voice: synthetic (Google Cloud Text-to-Speech, en-US-Neural2-D), declared on screen and in the video description; a human voice was the plan, the entrant had no recording time before the deadline (decision of 2026-09-05)
Music: none

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
decision shown three ways: the real film blocked on its content, a clean asset blocked because the
control itself failed (a fault injected on camera, the investigator naming the cause from Loki, a
human resolving the incident), the test clip passed once its study is on file. The stake and the
stack go inside the product frame, never on a slide. Script v6 of 2026-09-05; v5 (three runs with a
muted gate and a 16 minute prep) is in the git history.

## 1. The situation that hurts

[0:00] The console, idle. Over it, one line of Article 50 of the EU AI Act (in force 2026-08-02) as a text overlay for 4 s, then the console alone (cue stake). | "Since August 2026 the law wants generated content marked. Studios ship dozens of generated assets a week; the reviewer checks by hand, and nobody can prove which one was checked, or that the check itself was working."
[0:07] The console: the Crest clip on the stage, the four assets under it, the gate rows with their calibration lines read from Grafana ("caught N injected defects in 7 d, last success N min ago") (cue console_idle). | "Airlock: four gates, then a verdict that asks Grafana before it rules. Every line under a gate is Grafana's word, not the gate's."

## 2. The system acting: blocked on the content

[0:13] Click Run airlock on the Crest commercial (Prelinger Archives, 1960s, public domain, 30 s excerpt). The clip plays on the stage; the gate rows turn to RUNNING with the step named (cue crest_click). | "A real commercial with a real trademark on screen. The four gates run in parallel on Vertex AI Agent Engine while the clip plays."
[0:17] Provenance lands first: BLOCK, no C2PA manifest (cue provenance_done). | "Provenance is a cryptographic check, not an opinion: this film was shot decades before C2PA existed."
[0:22] Brand lands: BLOCK, the charter exclusions quoted with timestamps (cue brand_done). | "Brand: the charter forbids health claims, comparisons and children, and the house wordmark is not even there."
[0:29] Claim lands: BLOCK; a time chip of the claim finding is clicked at once and the clip seeks to the claim (cue claim_done). | "Click the time and the clip goes there. Every claim with its timestamp and its rule: a consumer testimonial under the Endorsement Guides, an efficacy claim under section five with no study on file."
[0:38] Rights lands: BLOCK, the Crest logo with its confidence, the ADA seal not cleared, the faces with no release (cue rights_done). | "Rights: Video Intelligence found the logo, the dental association's seal and the faces; the registry clears none of them."
[0:44] The verdict summary fills: BLOCK, content, needs a human, a punch-in on it; the Record segment shows the cost line and the incident id (cue verdict). | "Before it rules, the verdict asks Grafana five things about each gate, starting with: did Loki see this gate report on this very run. Then it writes the verdict back as an annotation, and the escalation opens the incident for the clearance owner. Half a dollar at list price, and it says so."

## 3. The system acting: blocked on the control itself

[0:58] Pick the Nimbus clean clip, caption "synthetic test asset, Veo 3.1 on Vertex AI, C2PA signed". Open the rights row and switch "Inject a fault" on; the amber badge "timeout fault injected" appears (cue fault_on). | "A clean generated asset, signed. Now we break the instrument on purpose: the rights gate will time out before it reads anything."
[1:04] Run; the clip plays; the rights row lands ERROR at once with the injected TimeoutError, the three others run (cue fault_click, cue rights_error). | "The gate fails in a millisecond and says so. The other three read the clip."
[1:14] Brand, claim and provenance land PASS; the cue is the last of the three to land, provenance lands first on this run (cue gates_done_2). | "Three gates pass. And the verdict still refuses."
[1:22] The verdict: BLOCK, motive control unavailable, "rights: control unavailable (instrument error ... seen by Grafana for this run, error rate 50 percent over 15 minutes)"; the investigation row runs under it, its tool calls listed (cue verdict_2, cue investigation). | "A control that failed is not a control. Then the investigator, the one language model agent in the pipeline, reads Loki through the same Grafana MCP server: this run's line, the previous runs, the alert that just fired."
[1:34] The Record segment: the Investigation note with the timestamp of the Loki line it cites, the incident id with its owner label; the "Airlock gate errors" alert firing in a Grafana insert for 4 s (cue investigation_note, cue alert_insert). | "It names the cause and the second it happened, and writes it into the incident. Grafana's alert rule fires on its own."
[1:44] Click "Mark reviewed by a human"; the incident reads resolved, the reviewed annotation id appears (cue resolve). | "A human closes the loop from the console: the incident resolves, and the decision lands on the dashboard as an annotation with the reviewer's role."

## 4. The system acting: passed on proof

[1:52] Pick "Nimbus test clip, study on file" (caption: the same clip as the test clip, with a substantiation file beside it in the bucket). Run; the clip plays (cue study_click). | "The Nimbus test clip blocks on one claim, nine out of ten sommeliers, with nothing behind it. The studio puts the study on file beside the asset. Same clip, same gates."
[1:58] Provenance lands PASS, "marked as generated" in the reason (cue provenance_done_3). | "Provenance: signed, and marked as generated, the machine-readable marking Article 50 asks for."
[2:04] Claim lands PASS naming the study (cue claim_done_3). | "Claim passes and names the study it rests on."
[2:20] Rights lands PASS after its wait; the verdict card: PASS, "all 4 gates PASS, seen by Grafana, healthy and calibrated", the annotation id, the decision note under it (cue rights_done_3, cue verdict_3). | "Every gate seen by Grafana on this run, healthy, and calibrated by this morning's proof: a scheduled job injects a real defect into every gate twice a day and a gate that misses loses its right to pass. This is the PASS the reviewer no longer signs by hand."

## 5. The result, in numbers

[2:32] The public Grafana dashboard: the verdict tiles, calibration catches and misses per gate, the daily proofs, the cost per check, the annotation markers of the three runs (cue dashboard). | "Every verdict is an annotation on this dashboard. Every block that needs a human is an incident that a human closes. Every gate proves itself twice a day, and the cost of every check is on the same screen."
[2:42] The PASS verdict card, held (cue landing). | "Nothing ships without a gate that has already caught a real defect, seen by Grafana. That is Airlock."

## Render checklist

- [ ] The Crest run measured once alone on the recording day; the rights gate costs 30 to 70 s whatever the input length (measured 2026-09-02), so each run is 40 to 90 s and the take is re-timed from the draft's cue log, not from this script's targets
- [ ] No muted prep and no staleness wait any more: the control beat is the injected fault, instantaneous by construction
- [ ] The daily proof of the morning read CAUGHT on every gate (`gcloud run jobs executions list`), so the PASS at the end is earned; the "Airlock gate errors" alert will fire during the take because of the injected fault, as intended
- [ ] The substantiation file present beside the asset in the bucket (`gs://airlock-agentic-cinema-assets/synthetic/nimbus-test-clip-substantiated.mp4.substantiation.yaml`)
- [ ] 1920x1080, 30 fps constant, 150 to 175 s, the render gates PASS (`AIRLOCK_RENDER_CHECK` when a checker is configured)
- [ ] Voice at -16 LUFS, true peak under -1 dBTP, no silence over 4 s, no black over 1.5 s at the open
- [ ] Subtitles burned in from this script; the synthetic voice declared on screen and in the YouTube description
