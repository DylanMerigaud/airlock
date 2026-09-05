# Airlock

Studios ship dozens of generated assets a week, and nobody can prove which one was checked, by
which rule, and whether the check itself was working. Airlock answers one question per asset:
can this ship, on what proof, and was the control that said so in a state to say it?

Try it, no login: https://airlock-console-771466810465.us-central1.run.app (pick an asset, run the airlock, read the trace; the two demo assets and a clean one that PASSes, or upload a 30 s clip).

![The reviewer console after the Crest commercial ran, one screen: the clip on the stage with the findings marked on the scrubber, the verdict and the checks list with one status line per gate on the right, the stats in the footer](docs/img/console-v3-crest-block-2026-08-29.png)

![The Airlock gates dashboard on Grafana Cloud, 2026-09-02, open on the last 7 days: verdicts, calibration catches and misses, seconds since each gate last succeeded, runs, errors, latency and blocks per gate, and the two cost panels (list price per check over 7 days, cost per gate run), with one annotation per verdict](docs/img/grafana-public-dashboard-2026-09-02.png)

Public dashboard (no login): https://narrowsubmarine1895.grafana.net/public-dashboards/97860661238c4536a743e0d858aef845

## What it does

Four gates read the asset, each against a named source of truth:

| gate | source of truth | what blocks |
|---|---|---|
| rights | Video Intelligence API (logos, faces, text, explicit content) against `rights-registry.yaml` | an identifiable brand or face the registry does not clear |
| claim | gemini-2.5-pro extracts every claim with timestamps; 16 CFR Part 255 and two ASA rulings map each kind (`rules/`) | a regulated claim with no substantiation on file |
| brand | gemini-2.5-flash reads the asset against `charter.yaml` | a missing wordmark, an exclusion, a forbidden colour, the wrong tone |
| provenance | c2pa-python verifies the C2PA manifest against `trust/trust-anchors.pem` | no manifest, a broken signature, an untrusted signer |

The brand gate's palette check rests on the model's estimate of the dominant colours under a JSON
schema, not on a measurement; a frame histogram (ffmpeg or PIL over sampled frames) is the follow-up,
noted 2026-09-05, not in this submission.

Then the verdict agent asks Grafana, through MCP, five questions about each gate before it rules:
whether Loki holds this run's event of the gate (LogQL `{app="airlock", gate="rights"} |= "<run id>"`,
retried while Loki ingests), then four PromQL questions: error ratio over 15 minutes and the runs it
rests on, seconds since the last success (informational), injected defects caught over 7 days, and
whether the last calibration run caught its defect. Two rules, both plain Python:

- **R1, control unavailable.** A gate whose event for this run Grafana cannot see, or whose own
  result is an error, or whose recent runs are mostly errors (at least half of at least two runs in
  15 minutes), forces BLOCK. The gate's own PASS does not count; Grafana's view of this run does. A
  muted gate pushes nothing, so Loki never sees its run and R1 fires by construction, on the run the
  judge muted, with no wait.
- **R2, uncalibrated.** A gate that has caught no injected defect, or whose last calibration run
  missed, is advisory: its PASS cannot contribute to a PASS verdict.

When Grafana Cloud itself is starting (the free stack pauses after idle days and answers 503 for about
two minutes), the verdict waits for it, up to three minutes, and says how long it waited; beyond that
the verdict is an ERROR "instrument error" that leaves its own sample in Grafana through the Influx
endpoint. The input may also inject a fault (`{"fault": {"rights": "timeout"}}`): the gate fails
before it spends anything, the error lands in Loki and in the counters like a real one, and the
verdict must catch it through Grafana.

The verdict is written back to Grafana as an annotation. When only a human can lift the BLOCK (a
control in a bad state, or missing paperwork such as a substantiation, a licence, a release), the
escalation agent opens a Grafana incident.

Every decision is a plain function under pytest; the models only read. ADK is the runtime
envelope; Grafana is asked before every verdict.

## Run it

```
uv sync                                                  # Python 3.12, google-adk, c2pa-python, Video Intelligence, google-genai
scripts/fetch_assets.sh                                  # the Prelinger commercial (public domain), hash checked
uv run pytest -q                                         # the rules, 64 tests, no cloud needed
scripts/with_env.sh uv run python -m airlock.run assets/real/CrestToothpa-18-48.mp4      # the four gates, locally
scripts/with_env.sh uv run adk run agents/pipeline "gs://<your bucket>/asset.mp4"         # the whole pipeline, verdict through Grafana
```

`scripts/with_env.sh` loads `.env.local` (copy `.env.example`) and pulls the secrets from the macOS
keychain; in the cloud they come from Secret Manager. The cloud side, in order:
`infra/gcp/bootstrap.sh`, `infra/gcp/secrets.sh`, `infra/mcp-grafana/deploy.sh`,
`scripts/grafana_bootstrap.py`, then `uv run adk deploy agent_engine --project <p> --region us-central1 --display_name airlock agents/pipeline`.
Every step and its output is in `docs/RUNS.md`.

## Architecture

```
  console (Next.js on Cloud Run)  ---- :streamQuery ---->  Vertex AI Agent Engine
    pick an asset, run, read the trace                       ADK SequentialAgent "airlock"
                                                               ParallelAgent "gates"
                                                                 rights      Video Intelligence + registry
                                                                 claim       gemini-2.5-pro + 16 CFR 255 + ASA
                                                                 brand       gemini-2.5-flash + charter
                                                                 provenance  c2pa-python + trust list
                                                               verdict   --McpToolset (streamable HTTP)-->  mcp-grafana on Cloud Run
                                                               escalation                                     |
                                                                                                              v
  gates push counters (Influx line protocol) and events (Loki)  ---->  Grafana Cloud: dashboard "Airlock gates",
                                                                        annotations, incidents
```

Inputs: a Prelinger commercial (real, public domain, `assets/real/SOURCE.md`), a Veo clip with an
injected claim and a real C2PA manifest (synthetic, labelled, `SYNTHETIC.md`), or a short upload.

## Calibration

`python -m airlock.calibrate` runs one real injected defect per gate through the real gate and
pushes the catch or the miss to Grafana. The ledger of 2026-08-28:

| gate | injected defect | caught | missed |
|---|---|---|---|
| rights | a real trademark the registry does not clear, real faces without a release | 1 | 0 |
| claim | an expert endorsement with nothing behind it (16 CFR 255.3) | 2 | 2 |
| brand | a pure red urgency banner the charter forbids | 1 | 0 |
| provenance | the manifest stripped; a signed copy with one byte flipped | 2 | 0 |

The two claim misses are real: one was a bug on GCS-only assets (fixed the same hour), the other
was `--defect-removed`, the deliberate miss that shows the verdict refusing a PASS from a gate whose
last calibration failed (`docs/RUNS.md`, verification C).

Since 2026-09-02 the control proves itself on a schedule: a Cloud Run job (`python -m
airlock.daily_proof`, `infra/gcp/daily_proof.sh`) runs the full calibration and then the clean clip
through the deployed pipeline at 00:00 and 12:00 UTC, and pushes `airlock_daily_proof_total` with the
outcome. A failed proof is not retried into a pass (the Cloud Run job runs with `--max-retries=0`
since 2026-09-05; before that, one retry turned two proofs that met a paused Grafana Cloud into
passes, `docs/RUNS.md`): the gate that missed loses its right to PASS on its own until a calibration
catches again, and every run in between is a BLOCK "uncalibrated control".

## The console

`console/`: Next.js on Cloud Run, one screen, the light palette and type of YouTube Studio, no
animation. The clip is the stage (it plays while the gates read it) with every timestamped finding
marked on the scrubber, Frame.io style; beside it the verdict, then a segmented control: Checks (one
status line per gate, YouTube Studio's Checks step, the calibration line read from Grafana under
each and a "mute telemetry" switch inside the row to disable a gate and watch the verdict refuse),
Findings (the thread, a click on a time seeks the clip) and Record (the rules cited, the C2PA line,
the annotation and the incident). Two more views: the Trace (raw agent events) and the BLOCK queue.
Lighthouse on the hosted URL: accessibility 100. Mock mode
(`AIRLOCK_MOCK=1`) replays recorded runs so it builds and runs without a credential
(`console/README.md`).

## The gates as MCP tools

`airlock_mcp/`: a FastMCP server on Cloud Run (https://airlock-mcp-771466810465.us-central1.run.app/mcp,
bearer required) exposing `check_rights`, `check_claim`, `check_brand`, `check_provenance`,
`check_all`, `verdict_rules` and `list_rules`, so another agent can run a gate on a GCS asset and
read the rules the verdict will apply. Client, connection snippets and deploy: `docs/AIRLOCK-MCP.md`.

## Evaluation

`scripts/eval_gates.py` runs the four gates on 16 assets, one at a time: 10 more Prelinger
commercials (Cheerios, Chevrolet, Ivory, Kodak, Folgers, Labatt's, Gilbert, Macleans, Scotties,
General Electric; `assets/real/eval/SOURCE.md`) and the 6 synthetic clips. `eval/EVAL.md`,
2026-08-29:

| gate | n | precision | recall | median latency | max |
|---|---|---|---|---|---|
| rights | 13 | 100% | 100% | 47.7 s | 457.9 s |
| claim | 3 | 100% | 100% | 18.9 s | 39.9 s |
| brand | 4 | 100% | 100% | 17.0 s | 31.1 s |
| provenance | 15 | 100% | 100% | 2 ms | 34 ms |

Cost at list price (`pricing.yaml`, Billing Catalog SKUs read 2026-08-29): median 0.52 USD per
30 s spot, 8.23 USD for the whole run (16 Video Intelligence minutes, 32 Gemini calls); the
Video Intelligence started minute is most of it, so an 8 s clip costs the same as a 30 s one.

Two limits the evaluation exposed, kept on purpose: Video Intelligence named the wrong company on
6 of the 10 real spots at high confidence (a 1955 Chevrolet read as "DeLorean Motor Company"); the
verdict held because the policy blocks any brand the registry does not clear, so the gate's reason
now says "a logo the registry does not know" and quotes the API's guess as a guess. And the raw
Veo output is not unsigned: it carries a Google-issued C2PA manifest, which the gate blocks as an
untrusted signer until the studio puts Google's certificate on its trust list.

## What is proven, and where

`docs/RUNS.md` carries every milestone with its command, output, annotation id and incident id:
the Agent Engine run of the real clip (BLOCK on content, annotation 9, incident 6), the run with
the rights telemetry dark for 16 minutes (BLOCK, control unavailable, annotation 7), the run after
a calibration miss (BLOCK, uncalibrated control, annotation 8), and the first PASS (annotation 10).

## Tests

Three commands, no cloud call in any of them:

```
uv run pytest -q                                       # the rules: gates, verdict (R1, R2, instrument error, paperwork), ledger, telemetry, the MCP server
uv run ruff check .                                    # lint (E, F, B, BLE, UP at 160 columns; the ignores and their reasons are in pyproject.toml)
uv run pyright airlock agents airlock_mcp scripts      # types, basic mode
```

The tests cover the line-protocol formatter, the four gate decisions, the verdict rules, the
calibration ledger (one series per injected defect), the shared telemetry pushers, the settings
module, and airlock-mcp (bearer, health route, tools that leave the event loop free).

## Synthetic inputs

`SYNTHETIC.md` names every synthetic element: the Veo clip, its overlays, its self-issued signing
certificate, the calibration variants. Everything else is real and named at its source.

## Layout

- `airlock/` gates, verdict rules, calibration ledger, telemetry push, the Grafana MCP toolset
- `agents/pipeline/` the ADK pipeline (the M1 spike agent, `agents/spike/`, was deleted on 2026-09-05 with its engine; `docs/RUNS.md` M1 keeps its record)
- `console/` the reviewer console (Next.js); `airlock_mcp/` the gates as MCP tools; `infra/` Google Cloud, Cloud Run and Secret Manager scripts
- `rules/` 16 CFR 255 and the ASA rulings; `charter.yaml`, `rights-registry.yaml`, `trust/`
- `scripts/` Grafana bootstrap, asset build, Agent Engine query; `tests/`; `docs/RUNS.md`

Built for Agentic Cinema (Google Cloud, Grafana Labs track), 2026-08-28 to 2026-09-09, by Dylan
Merigaud. Apache-2.0.
