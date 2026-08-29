# Airlock reviewer console

The surface a brand-safety reviewer opens: watch the clip, run it through the four Airlock
gates, and read every finding against the second of the clip it was read at. The console never
shows a PASS that Grafana could not back: every check row carries what the instrument itself
reports, and a gate that has never caught an injected defect is marked ADVISORY.

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
| Nimbus | `fixtures/run-nimbus-block.jsonl` | Three gates PASS, claim BLOCK on 16 CFR 255.3, no human needed |
| Nimbus clean | `fixtures/run-clean-pass.jsonl` | Four gates PASS and a PASS verdict, healthy and calibrated, no human needed |
| An uploaded clip | `fixtures/run-nimbus-instrument-error.jsonl` | A gate that failed while running, so nothing is cleared |

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
| `GET /api/health` | The three PromQL answers per gate (error rate, seconds since success, calibration catches over 7d) through the Grafana datasource API. Cached 20 s. |
| `GET /api/stats` | Seven day verdict and incident totals, plus how many gates are calibrated. Cached 20 s. |
| `GET /api/asset/[id]` | Streams a preloaded clip out of Cloud Storage with the server credentials, for the player on the stage. In mock mode it answers 503, so the stage falls back to the poster and says so. |

Every one of them runs on the Node runtime. When Grafana cannot be reached the stat tiles read
`unavailable` in red and say why on hover: no placeholder number is ever shown.

## The three preloaded assets

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

- The block queue is per browser, in `localStorage`. Nothing about a run leaves the session except
  what the agents themselves wrote to Grafana.
- A finding becomes a marker on the scrubber when its sentence names a second of the clip, which
  is parsed narrowly: `at 16.12s`, `first at 7.5s`, `at 3.0s`. A bare `533 s ago` in a health
  line is a duration, not a position, and never becomes one (`src/lib/timecodes.ts`).
- "Mark reviewed by a human" flips the decision record locally. In production it closes the
  incident.
- Mock health mirrors `fixtures/run-nimbus-block.jsonl`, so the claim gate reads degraded at a
  33 percent error rate there. The uncalibrated ADVISORY state is served by the same code path
  when Grafana reports no calibration catch for a gate.
