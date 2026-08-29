# Devpost submission text (Agentic Cinema, Grafana Labs track)

Name: Airlock
Tagline: Studios ship dozens of generated assets a week and nobody can prove which one was checked, by which rule, or whether the check itself was working.

## What it does

Airlock decides whether a generated media asset can ship, on proof. Four gates read the asset,
each against a named source of truth: rights (the Video Intelligence API against a rights
registry), claim (every spoken or on-screen claim extracted with timestamps, mapped to 16 CFR Part
255 and two real ASA rulings), brand (the asset against a brand charter) and provenance (the C2PA
manifest verified cryptographically against a trust list). Then a verdict agent asks Grafana,
through MCP, four PromQL questions about each gate before it is allowed to rule: error rate over
15 minutes, seconds since the gate last succeeded, injected defects caught over 7 days, and whether
the last calibration run caught its defect. A gate Grafana cannot see succeed forces a BLOCK
"control unavailable"; a gate that never caught a real defect is advisory and cannot contribute to
a PASS. The verdict is written back to the Grafana dashboard as an annotation, and when only a
human can lift the BLOCK, an incident is opened in Grafana IRM. On the demo assets it takes 48 s
from upload to verdict for an 8 s clip and 119 s for a 30 s commercial.

## How I built it

All decision logic is plain, unit-tested Python (41 tests, none of them calls a model): the four
gate decisions, the two verdict rules, the escalation rule. Google ADK is the runtime envelope: a
SequentialAgent whose first step is a ParallelAgent of the four gates (each a BaseAgent around a
plain function, run in a thread so they really overlap), then a verdict BaseAgent, then an
escalation BaseAgent, deployed on Vertex AI Agent Engine. The models only read: gemini-2.5-pro
extracts claims with timestamps (flash mis-scales video timestamps, measured), gemini-2.5-flash
reads the charter. The Video Intelligence API finds logos, faces, text and explicit content; the
c2pa-python library verifies manifests. Grafana is reached through the open-source mcp-grafana
server deployed on Cloud Run in streamable HTTP mode behind its own bearer, from ADK's McpToolset
with a header provider; the gates push their counters through Grafana Cloud's Influx line-protocol
endpoint and their events through Loki. A calibration ledger (`python -m airlock.calibrate`) runs
one real injected defect per gate through the real gate and pushes the catch or the miss, which is
what gives a gate the right to block. The reviewer console is a Next.js app on Cloud Run that
streams the Agent Engine run as server-sent events.

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
trust list feature.

## Accomplishments

Ten annotations and five incidents on the Grafana stack in one day, each one a verdict a judge can
read back: the real 1960s commercial blocked on four gates, the run with the rights telemetry dark
for 16 minutes blocked as "control unavailable" although every gate had passed, the run after a
calibration miss blocked as "uncalibrated control", and the first PASS only once all four gates
were healthy and calibrated on a clean signed asset.

## Built With

python, google-adk, vertex-ai, agent-engine, gemini, cloud-run, video-intelligence, secret-manager,
mcp, mcp-grafana, grafana-cloud, loki, c2pa, veo, next.js, typescript

## Track requirements

- [x] Google Cloud in the product: Vertex AI Agent Engine, Cloud Run, Video Intelligence API, Secret Manager, Cloud Storage (`infra/`, `docs/RUNS.md`)
- [x] Gemini on Vertex AI inside the shipped product, not as a dev tool (`airlock/gemini.py`, `airlock/gates/claim.py`, `airlock/gates/brand.py`)
- [x] An agent built with ADK and deployed on Agent Engine (`agents/pipeline/agent.py`, `docs/RUNS.md` M1 and M3)
- [x] Grafana Labs track: the agent reads Grafana through MCP before every verdict and writes back an annotation and an incident (`agents/pipeline/agent.py`, `docs/RUNS.md` verifications A, B, C)
- [x] Public repository under an OSI licence: Apache-2.0 (`LICENSE`), github.com/DylanMerigaud/airlock
- [x] Hosted URL a judge can open without a login: https://airlock-console-771466810465.us-central1.run.app (Cloud Run, `docs/RUNS.md` M4)
- [ ] Demo video of 3 minutes or less (M5)
- [x] Every synthetic input named (`SYNTHETIC.md`); every real input named with its source and licence (`assets/real/SOURCE.md`)

## Try it

Open https://airlock-console-771466810465.us-central1.run.app, pick the Crest commercial (Prelinger Archives, public domain, 30 s) and run
the airlock: expect four BLOCKs, the verdict citing 16 CFR 255.2(a) and the missing C2PA manifest,
an annotation on the public dashboard, and an incident. Pick the Nimbus test clip (synthetic,
labelled): expect rights, brand and provenance PASS, claim BLOCK on "Recommended by 9 out of 10
sommeliers" under 16 CFR 255.3. Pick the Nimbus clean clip: expect the PASS, earned by four healthy,
calibrated gates. Switch a gate's "mute telemetry" on and rerun after 15 minutes: the verdict refuses
to PASS whatever the gates say, because Grafana no longer sees the control succeed. Public dashboard:
https://narrowsubmarine1895.grafana.net/public-dashboards/97860661238c4536a743e0d858aef845
