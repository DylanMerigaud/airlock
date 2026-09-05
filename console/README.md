# Airlock reviewer console

The surface a brand-safety reviewer opens: watch the clip, run it through the four Airlock
gates, and read every finding against the second of the clip it was read at. The console never
shows a PASS that Grafana could not back: every check row carries what the instrument itself
reports, the verdict row says whether Grafana saw each gate's event for this very run (the verdict
asks Loki for it, so a muted gate blocks on the run that muted it), and a gate that has never
caught an injected defect is marked ADVISORY.

Three views in the top bar. **Review** is one screen: above 1100 px wide it fits the viewport
with no page scroll. The clip holds the left with its scrubber, one marker per timestamped
finding coloured by the gate that wrote it, and the asset strip under it. The right column
carries the verdict and a segmented control, **Checks | Findings | Record**, so the reviewer
switches what they read while the clip stays on screen; each segment scrolls inside its own
region. **Trace** is the raw event timeline of the run. **Queue** is the session's BLOCK
worklist. The five seven-day totals and the spec line sit in one thin bar at the bottom.

The palette is YouTube Studio's light theme applied literally, and the type is Roboto with
Roboto Mono for ids, rules, timestamps and calibration lines. Nothing on the page loops,
blinks or sweeps: a running gate shows a static icon and says its step in words, and the only
motion is a single 160 ms fade when a row arrives.

Next.js 15 App Router, TypeScript, Tailwind 4, pnpm. Apache-2.0.

## Run locally in mock mode, three commands

Mock mode needs no cloud credentials. It replays a run recorded against the real pipeline over
the same SSE relay the live agent uses, and serves fixture health and stats marked MOCK in the
interface. Each preloaded asset has its own recording:

| Asset picked | Fixture replayed | What it shows |
| --- | --- | --- |
| Crest | `fixtures/run-crest-incident.jsonl` | BLOCK on content, four failing gates, an incident opened |
| Nimbus | `fixtures/run-nimbus-block.jsonl` | Three gates PASS, claim BLOCK on 16 CFR 255.3, a human needed, an incident opened or joined |
| Nimbus, study on file | `fixtures/run-substantiated-pass.jsonl` | The same clip with its substantiation file beside it in the bucket: claim PASS naming the study, PASS verdict |
| Nimbus clean | `fixtures/run-clean-pass.jsonl` | Four gates PASS and a PASS verdict, healthy and calibrated, no human needed |
| An uploaded clip | `fixtures/run-nimbus-instrument-error.jsonl` | The clean clip with a timeout fault injected into the rights gate: BLOCK control unavailable, the investigator's root cause from Loki, an incident |

Every fixture was re-recorded on 2026-09-05 with `scripts/record_fixture.py` against the deployed pipeline (the
investigator, the run id in every event, the per-run Loki read).

```
pnpm install
cp .env.example .env.local && sed -i '' 's/^AIRLOCK_MOCK=0/AIRLOCK_MOCK=1/' .env.local
AIRLOCK_MOCK=1 pnpm dev
```

Open http://localhost:3000 and press Run airlock.

## Run against the real agent

Needs Application Default Credentials on the machine (`gcloud auth application-default login`)
and a Grafana service account token.

```
cp .env.example .env.local
# fill AGENT_ENGINE_RESOURCE and GRAFANA_SERVICE_ACCOUNT_TOKEN, keep AIRLOCK_MOCK=0
pnpm build && pnpm start
```

What each variable does is written in `.env.example`. `GRAFANA_SERVICE_ACCOUNT_TOKEN` is the only
secret; locally it comes from the keychain loader in `infra/gcp/secrets.sh`, on Cloud Run from
Secret Manager. Never commit a filled `.env`.

## Deploy

```
export AGENT_ENGINE_RESOURCE=projects/771466810465/locations/us-central1/reasoningEngines/<id>
bash ../infra/console/deploy.sh
```

Cloud Run builds from source with the `Dockerfile` here (multi-stage, node:22-alpine, standalone
output, listening on `$PORT`). The script prints the service URL when it is done.

## What the console talks to

| Route | What it does |
| --- | --- |
| `POST /api/run` | Resolves the asset to a `gs://` URI, calls Vertex AI Agent Engine `streamQuery`, relays every ADK event to the browser as SSE. Upstream timeout 15 minutes, nothing buffered. |
| `POST /api/upload` | One MP4 up to 50 MB into `gs://$AIRLOCK_ASSETS_BUCKET/uploads/`. The browser refuses clips over 30 s before the upload starts. |
| `GET /api/health` | The verdict's PromQL per gate (error ratio and runs over 15 minutes, seconds since success, calibration catches over 7d, whether the last calibration caught), read from `src/lib/promql.json`, which `scripts/export_promql.py` writes from `airlock.verdict.promql_questions` (a test fails on drift). Cached 20 s. |
| `GET /api/incidents` | Grafana Incident's open Airlock incidents (drills included), the Queue tab. |
| `POST /api/incident/resolve` | Resolves an Airlock incident (`IncidentsService.UpdateStatus`, after reading it back and refusing any other title) and writes an annotation tagged `airlock, reviewed` with the reviewer's role. Same per-caller limit as `/api/run`. |
| `GET /api/stats` | Seven day verdict and incident totals, plus how many gates are calibrated. Cached 20 s. |
| `GET /api/asset/[id]` | Streams a preloaded clip out of Cloud Storage with the server credentials, for the player on the stage. In mock mode it answers 503, so the stage falls back to the poster and says so. |

Every one of them runs on the Node runtime. While Grafana has not answered yet the stat tiles and
the calibration lines are grey placeholder bars, never a number and never a red word. When a route
answers `ok: false` (a paused Grafana Cloud free stack answers 503 "Loading" for about two minutes
while it wakes) the console retries every 10 s for 3 minutes, then every 60 s, keeps the last good
payload on screen, and says "Grafana Cloud is starting, retrying" in the footer; the tiles read
`unavailable` in red, with the reason on hover, only once that budget is spent with nothing to show.
Nothing polls while every route answers `ok: true`: one refresh on mount and one per settled run.

## The four preloaded assets

- **Crest Toothpaste Commercial**, Prelinger Archives, public domain, 30 s excerpt, real footage.
  Expected: four blocks (trademark not cleared, unsubstantiated claims, off charter, no C2PA
  manifest).
- **Nimbus test clip**, synthetic, generated with Veo 3.1 on Vertex AI and C2PA signed, 8 s.
  Expected: rights PASS, claim BLOCK on 16 CFR 255.3, brand PASS, provenance PASS. It is labelled
  as a synthetic test asset wherever it appears.
- **Nimbus clean clip**, synthetic, same generator and the same C2PA signature, 8 s. The asset
  that should PASS: four gates PASS and a PASS verdict when every gate is healthy and calibrated.
  Labelled as a synthetic test asset too.

## Muting a gate's telemetry

Every check row expands onto a **Mute telemetry** switch, off by default. It is how the demo shows
that the console never takes a gate's own word for it: the gate still runs and still answers, but
it pushes nothing to Grafana, and the verdict agent has to notice through Grafana that the control
went dark. A muted gate carries a `muted` chip on its check row and on its timeline rows.

The switch state belongs to the run: the browser sends `{ "asset": "...", "mute": ["rights"] }` to
`POST /api/run`, the route hands the pipeline
`{"gcs_uri": "...", "asset_id": "...", "mute": ["rights"]}` instead of the bare URI, and the gate
events come back carrying `telemetry_muted`. It stays armed between runs until it is switched back
off. In mock mode the chips come from the switches and from the recording: the run replayed for
Crest was itself recorded with the rights gate muted, so its rights row carries the chip.

## Notes for anyone reading the code

- The Queue tab lists Grafana Incident's open Airlock incidents (`GET /api/incidents`), each with a
  Re-run and a Resolve action; `localStorage` only holds the offline fallback, labelled as such. The
  last settled run (events and verdict) is kept in `sessionStorage`, keyed by its `startedAt`, and restored on mount with a "restored" note
  in the Record segment, so following the Grafana link and coming back loses nothing. Nothing about
  a run leaves the session except what the agents themselves wrote to Grafana.
- The calibration line under a gate before a run reads one of five states derived from Grafana's
  four numbers (`src/lib/gate-state.ts`, the same PromQL the verdict asks): `degraded` (errors in 15 minutes, amber), `unproven` (no
  success sample in 7 d, amber), `never calibrated: ADVISORY` (amber), `idle` (no error, last
  success older than 900 s, soft ink: the gates run before the verdict asks Grafana, so the run
  re-proves it) and `healthy`. The verdict rules on the Python side are untouched by this wording.
- A finding becomes a marker on the scrubber when its sentence names a second of the clip, which
  is parsed narrowly: `at 16.12s`, `first at 7.5s`, `at 3.0s`. A bare `533 s ago` in a health
  line is a duration, not a position, and never becomes one (`src/lib/timecodes.ts`).
- "Mark reviewed by a human" posts to `/api/incident/resolve`: the incident is resolved in Grafana
  Incident and an annotation tagged `reviewed` carries the reviewer's role and the verdict summary; the
  Record shows the resolved status and the annotation id.
- Mock health mirrors `fixtures/run-nimbus-block.jsonl`, so the claim gate reads degraded at a
  33 percent error rate there. The uncalibrated ADVISORY state is served by the same code path
  when Grafana reports no calibration catch for a gate.
