# Devpost submission text (Agentic Cinema, Grafana Labs track)

Name: Airlock
Tagline: Studios ship dozens of generated assets a week and nobody can prove which one was checked, by which rule, or whether the check itself was working.
Video: https://youtu.be/xWJ0nMu5cqM

## What it does

Airlock decides whether a generated media asset can ship, on proof. Four gates read the asset,
each against a named source of truth: rights (the Video Intelligence API against a rights
registry), claim (every spoken or on-screen claim extracted with timestamps, mapped to 16 CFR Part
255 and two real ASA rulings), brand (the asset against a brand charter) and provenance (the C2PA
manifest verified cryptographically against a trust list). Then a verdict agent asks Grafana,
through MCP, five questions about each gate before it is allowed to rule: whether Loki holds this
run's event of the gate, then four PromQL questions (error ratio over 15 minutes and the runs behind
it, seconds since the gate last succeeded, injected defects caught over 7 days, and whether the last
calibration run caught its defect). A gate whose run Grafana did not see forces a BLOCK "control
unavailable"; a gate that never caught a real defect is advisory and cannot contribute to a PASS.
The verdict is written back to the Grafana dashboard as an annotation; then an investigator agent
(gemini-2.5-flash, the same Grafana MCP tools) reads this run's Loki lines, the previous runs and the
alert rules and names the root cause with the timestamp it rests on, and when only a human can lift
the BLOCK, an incident is opened in Grafana IRM (or the open one for the same asset joined, as a drill
on the free stack) carrying that note, which the reviewer closes from the console. A check takes
one to four minutes, almost all of it the Video Intelligence operation: measured on the hosted
console, the 8 s clean clip took 38 s (`docs/RUNS.md`, the cold judge pass of 2026-09-02,
annotation 52) and 243 s (the console v3.1 verification the same night, annotation 55), and 189 s
from Agent Engine while another check ran (audit item 4, annotation 50); the 30 s Crest excerpt took
72 s (first console verification, 2026-08-29) and 78 s (cold judge, annotation 51) on the console
and 119 s from Agent Engine with three Video Intelligence jobs overlapping (verification A). Every
check reports what it cost at list price (tokens, video minutes, dollars), pushed to Grafana beside
the verdict.
The control also proves itself twice a day: a scheduled job re-runs every injected defect and one
clean clip, and a gate whose defect slipped through loses its right to PASS until it catches again.

## How I built it

All decision logic is plain, unit-tested Python (64 tests, none of them calls a model): the four
gate decisions, the two verdict rules, the escalation rule. Google ADK is the runtime envelope: a
SequentialAgent whose first step is a ParallelAgent of the four gates (each a BaseAgent around a
plain function, run in a thread so they really overlap), then a verdict BaseAgent, then an
escalation BaseAgent, deployed on Vertex AI Agent Engine. The models label, the rules decide:
gemini-2.5-pro extracts every claim with its timestamps, quote and kind under a JSON schema (flash
mis-scales video timestamps, measured), gemini-2.5-flash reads the asset against the charter under
a schema (wordmark seen, dominant colours, tone words); the claim and brand decisions are plain
functions over those labels, so a wrong label is a wrong decision, which is what the calibration
ledger exists to catch. The Video Intelligence API finds logos, faces, text and explicit content; the
c2pa-python library verifies manifests. Grafana is reached through the open-source mcp-grafana
server deployed on Cloud Run in streamable HTTP mode behind its own bearer, from ADK's McpToolset
with a header provider; the gates push their counters through Grafana Cloud's Influx line-protocol
endpoint and their events through Loki. A calibration ledger (`python -m airlock.calibrate`) runs
one real injected defect per gate through the real gate and pushes the catch or the miss, which is
what gives a gate the right to block. The reviewer console is a Next.js app on Cloud Run that
streams the Agent Engine run as server-sent events. The four gates are also published as MCP
tools (`airlock-mcp`, FastMCP on Cloud Run behind a bearer) so another agent can call a gate on
a GCS asset and read the rules the verdict applies.

## Challenges

The instrument that runs green while measuring nothing was the whole point, and it bit the build
twice on the first day: a gate that failed on GCS-only assets recorded a calibration miss (kept in
the ledger as a miss), and a race in the Gemini client construction made a gate error under
parallel load, which the verdict then reported as "control unavailable, error rate 20 percent over
15 minutes" on a run where every gate had just passed. The hosted Grafana MCP endpoint is browser
OAuth, so the open-source server runs on Cloud Run. Grafana Incident on a fresh free stack refuses
API calls until the app is opened once, so the escalation carries a fallback annotation. The Video
Intelligence API takes 30 s alone and 108 s when three jobs overlap, which is why the gates run in
parallel and the real demo asset is a 30 s excerpt. And a self-issued C2PA signer validates as
"untrusted" until it is on the reader's trust list, which is the correct behaviour and became the
trust list feature. And the Grafana Cloud free stack pauses after idle days and answers 503 while it
wakes: the scheduled proof failed on its first attempt twice for that reason (Cloud Run job
executions `airlock-daily-proof-877cd` at 2026-09-04 12:05 UTC and `airlock-daily-proof-kwqbk` at
2026-09-05 00:04 UTC, `list_datasources` answered status 503) and passed on the job's retry,
so a Cloud Scheduler job now GETs the console health route every 30 minutes to keep the stack awake
(`infra/gcp/keepalive.sh`).

## Accomplishments

An evaluation on 16 assets (10 more real Prelinger commercials and 6 synthetic clips), reproducible
from the repository (`scripts/fetch_assets.sh` cuts the excerpts from archive.org and checks their
hashes) and scored per gate and per rule against a hand-labelled manifest: by status, 100 percent
precision and recall on every gate (rights 10 of 10 on n=16, claim 3 of 3 on n=5, brand 2 of 2 on
n=6, provenance 14 of 14 on n=16); per rule, every expected rule fired except the unknown-brand rule
on one spot where Video Intelligence found no logo (9 of 10), and one forbidden rule fired (explicit
content on a 1963 family party, 0 of 1); the brand on screen was named on 4 of 10 real spots. A
median of 0.52 USD per 30 s spot at list price (n=16), 41.1 s median for the rights gate and 2 ms
for provenance (`eval/EVAL.md`, run of 2026-09-05, the misses in its "Surprises" section). And
annotations and incidents on the Grafana stack from the first day, each one a verdict a judge can
read back: the real 1960s commercial blocked on four gates, the run with the rights telemetry dark
for 16 minutes blocked as "control unavailable" although every gate had passed, the run after a
calibration miss blocked as "uncalibrated control", and the first PASS only once all four gates
were healthy and calibrated on a clean signed asset.

## Built With

python, google-adk, vertex-ai, agent-engine, gemini, cloud-run, video-intelligence, secret-manager,
mcp, fastmcp, mcp-grafana, grafana-cloud, loki, c2pa, veo, next.js, typescript

## Track requirements

- [x] Google Cloud in the product: Vertex AI Agent Engine, Cloud Run, Video Intelligence API, Secret Manager, Cloud Storage (`infra/`, `docs/RUNS.md`)
- [x] Gemini on Vertex AI inside the shipped product, not as a dev tool (`airlock/gemini.py`, `airlock/gates/claim.py`, `airlock/gates/brand.py`)
- [x] An agent built with ADK and deployed on Agent Engine (`agents/pipeline/agent.py`, `docs/RUNS.md` M1 and M3)
- [x] Grafana Labs track: the agent reads Grafana through MCP before every verdict and writes back an annotation and an incident (`agents/pipeline/agent.py`, `docs/RUNS.md` verifications A, B, C)
- [x] Public repository under an OSI licence: Apache-2.0 (`LICENSE`), github.com/DylanMerigaud/airlock
- [x] Hosted URL a judge can open without a login: https://airlock-console-771466810465.us-central1.run.app (Cloud Run, `docs/RUNS.md` M4)
- [x] Demo video of 3 minutes or less: https://youtu.be/xWJ0nMu5cqM (draft 5, synthetic voice; the final replaces it)
- [x] Every synthetic input named (`SYNTHETIC.md`); every real input named with its source and licence (`assets/real/SOURCE.md`)

## Try it

Open https://airlock-console-771466810465.us-central1.run.app, pick the Crest commercial (Prelinger Archives, public domain, 30 s) and run
the airlock: expect four BLOCKs, the verdict citing 16 CFR 255.2(a) and the missing C2PA manifest,
an annotation on the public dashboard, and an incident. A check takes one to three minutes; the
rights gate waits for the Video Intelligence API, which slows down when several checks overlap. Pick the Nimbus test clip (synthetic,
labelled): expect rights, brand and provenance PASS, claim BLOCK on "Recommended by 9 out of 10
sommeliers" under 16 CFR 255.3, and a decision note from the investigator. Pick "Nimbus test clip,
study on file": the same clip with its substantiation file beside it in the bucket, claim PASS naming
the study, a PASS verdict. Pick the Nimbus clean clip: the PASS, earned by four gates seen by Grafana
on this run, healthy and calibrated. Then break the control on purpose: open the rights row, switch
"Inject a fault" on and rerun; the gate fails before it spends anything, the verdict refuses ("control
unavailable"), the investigator reads Loki and names the failure with its timestamp, the "Airlock gate
errors" alert fires, and an incident opens that you can resolve from the Record segment (the
reviewed annotation lands on the dashboard). Or switch "Mute telemetry" on and rerun: Loki never sees
that gate report for this run, so the verdict refuses at once, whatever the gate said. Public dashboard:
https://narrowsubmarine1895.grafana.net/public-dashboards/97860661238c4536a743e0d858aef845

## Devpost draft

Draft created 2026-09-02, not submitted: https://devpost.com/software/airlock-s2kidr (edit:
https://devpost.com/submit-to/30721-agentic-cinema-the-blockbuster-hackathon/manage/submissions/1117836-airlock/project-overview).
The video slot holds draft 5 (synthetic voice) until the final replaces it. Additional info completed
on 2026-09-02 (country of residence France, first time using Grafana tools: yes): 4 of 5 steps done,
Devpost flags nothing missing. The Submit step (rules checkbox and the button) is left for 2026-09-08.
