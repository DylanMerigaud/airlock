# Airlock

Studios ship dozens of generated assets a week, and nobody can prove which one was checked, by
which rule, and whether the check itself was working. Airlock answers one question per asset:
can this ship, on what proof, and was the control that said so in a state to say it?

Try it, no login: https://airlock-console-771466810465.us-central1.run.app (pick an asset, run the airlock, read the trace; four presets: a real 1960s commercial that blocks, a synthetic test clip that blocks on one claim, the same clip with its study on file that passes, a clean clip that passes; or upload a 30 s clip; break the control with the fault switch and watch the verdict refuse).

![The reviewer console after the Crest commercial ran, one screen: the clip on the stage with the findings marked on the scrubber, the verdict and the checks list with one status line per gate on the right, the stats in the footer](docs/img/console-v3-crest-block-2026-08-29.png)

![The Airlock gates dashboard on Grafana Cloud, 2026-09-02, open on the last 7 days: verdicts, calibration catches and misses, seconds since each gate last succeeded, runs, errors, latency and blocks per gate, and the two cost panels (list price per check over 7 days, cost per gate run), with one annotation per verdict](docs/img/grafana-public-dashboard-2026-09-02.png)

Public dashboard (no login): https://narrowsubmarine1895.grafana.net/public-dashboards/97860661238c4536a743e0d858aef845

## What it does

Four gates read the asset, each against a named source of truth:

| gate | source of truth | what blocks | what it cites |
|---|---|---|---|
| rights | Video Intelligence API (logos, faces, text, explicit content) against `rights-registry.yaml` | a brand the registry does not clear (logo, or its name token-wise across the on-screen text lines), a face with no release for this asset, explicit content | the registry entry and its note |
| claim | gemini-2.5-pro extracts every claim with timestamps and a kind; the rule maps each kind (`rules/`) | a regulated claim with no substantiation on file (`<asset>.substantiation.yaml`, beside the asset locally or in the bucket, matched on the normalised quote); an endorser's undisclosed material connection | endorsements: 16 CFR 255.2 (consumer testimonial), 255.3 (expert), 255.4 (organisation), 255.5 (material connection); the advertiser's own efficacy, health, comparative and superlative claims: FTC Act section 5 and the FTC Policy Statement Regarding Advertising Substantiation (1983), CAP Code 3.7; a comparison also 16 CFR 14.15 and CAP 3.32; the ASA ruling whose claim shape matches. Puffery and price are advisory. |
| brand | gemini-2.5-flash reads the asset against `charter.yaml` | a missing wordmark, an exclusion, a forbidden colour, the wrong tone | the charter line |
| provenance | c2pa-python verifies the C2PA manifest against `trust/trust-anchors.pem` and reads its `c2pa.actions` | no manifest, a broken signature, an untrusted signer | the manifest's `digitalSourceType`: `trainedAlgorithmicMedia` is the machine-readable generated-content marking (EU AI Act Article 50); a trusted manifest without it PASSes with an advisory |

Known gaps a clearance desk would still check by hand: **music and artwork** (Video Intelligence
reads no audio and computes no fingerprint; a cue sheet is not read), **minors** (Video Intelligence
gives no age, so a child's face gets the adult rule and 16 CFR 255.6 is never applied), **the
market** (the US and UK rules are both cited on every claim; the gate does not know where the
asset airs), and **the FDA side of a health claim** (a cavity or decay claim on toothpaste is an
OTC drug claim; the gate says so in the reason and cites nothing further).

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

The verdict is written back to Grafana as an annotation. Then the investigator, the one LLM agent of
the pipeline (an ADK `LlmAgent` on gemini-2.5-flash with the same mcp-grafana toolset), reads this
run's Loki lines, the previous runs of the failing gate, the counters and the state of the Airlock
alert rules, in at most six tool calls, and writes a note of at most sixty words that names the cause
with the timestamp of the log line it rests on (`ROOT CAUSE:` on a control motive, `DECISION NOTE:` on
a content verdict or a PASS); the verdict never depends on it, and any failure becomes a fallback note.
When only a human can lift the BLOCK (a control in a bad state, or missing paperwork such as a
substantiation, a licence, a release), the escalation agent opens a Grafana incident labelled
`owner:platform` or `owner:clearance`, or joins the open incident of the same asset and motive, with
the note and the Loki lines it cites; the reviewer closes it from the console, which writes an
annotation tagged `reviewed`. On the free stack the incidents are opened as drills
(`AIRLOCK_INCIDENT_DRILL`, `true` unless set to `false` in the Agent Engine env): real Grafana
Incident objects, flagged so a judge's runs do not pile up as production incidents. Five alert rules provisioned by `scripts/grafana_bootstrap.py` tell
someone when the control itself fails ("Airlock daily proof failed", "Airlock gate errors",
"Airlock calibration missed", "Airlock verdict could not reach Grafana", and the dead man's switch
"Airlock daily proof did not run", which fires on the ABSENCE of a proof sample rather than on a
value), routed to an email contact point.

Where the decisions live: the verdict rules, the escalation rule, the rights rule and the provenance
rule are plain functions under pytest on inputs a service measured (Video Intelligence annotations,
a C2PA validation). The claim and brand gates decide on labels the model produced under a JSON
schema (the kind of each claim and its quote; whether the wordmark was seen, the dominant colours,
the tone words): the rule that turns those labels into a BLOCK is a plain function, the labels are
the model's, so a wrong label is a wrong decision. ADK is the runtime envelope; Grafana is asked
before every verdict.

## Run it

```
uv sync                                                  # Python 3.12, google-adk, c2pa-python, Video Intelligence, google-genai
scripts/fetch_assets.sh                                  # the Prelinger commercial and the ten eval excerpts (public domain), hash checked
uv run pytest -q                                         # the rules and the eval scoring, no cloud needed
scripts/with_env.sh uv run python -m airlock.run assets/real/CrestToothpa-18-48.mp4      # the four gates, locally
scripts/with_env.sh uv run adk run agents/pipeline "gs://<your bucket>/asset.mp4"         # the whole pipeline, verdict through Grafana
```

`scripts/with_env.sh` loads `.env.local` (copy `.env.example`) and pulls the five secrets from the
macOS keychain of the author's account. On another machine skip it and export them yourself before
the command: `GRAFANA_SERVICE_ACCOUNT_TOKEN` (a Grafana service account token with editor rights),
`GRAFANA_INFLUX_TOKEN` and `GRAFANA_LOKI_TOKEN` (the stack's write token, the same value for both
on Grafana Cloud), `GRAFANA_OTLP_TOKEN` (an access policy token with the `traces:write` scope; unset
means no traces, the rest runs) and `AIRLOCK_MCP_TOKEN` (the bearer you give mcp-grafana). In the
cloud they come from Secret Manager (`infra/gcp/secrets.sh`; the traces token is `grafana-traces-token`).

What a judge changes to run it on their own project, all read from env with the author's values as
defaults: the project (`GOOGLE_CLOUD_PROJECT` in `.env.local`, `AIRLOCK_PROJECT` for the scripts
and in `agents/pipeline/.agent_engine_config.json`; `infra/gcp/bootstrap.sh` also takes
`AIRLOCK_BILLING` and `AIRLOCK_ACCOUNT`), the assets bucket (`AIRLOCK_ASSETS_BUCKET`, default
`airlock-agentic-cinema-assets`), the deployed engine (`AGENT_ENGINE_RESOURCE`, the resource name
`adk deploy` prints), the Grafana stack (`GRAFANA_URL`; `GRAFANA_INFLUX_URL` and
`GRAFANA_INFLUX_USER`, `GRAFANA_LOKI_URL` and `GRAFANA_LOKI_USER`: the push URLs and numeric
instance ids from the stack's Prometheus and Loki "Details" pages, in `.env.local` and in the same
config file) and the mcp-grafana URL (`AIRLOCK_MCP_URL`, printed by `infra/mcp-grafana/deploy.sh`).
The cloud side, in order: `infra/gcp/bootstrap.sh`, `infra/gcp/secrets.sh`,
`infra/mcp-grafana/deploy.sh`, `scripts/grafana_bootstrap.py`, then
`uv run adk deploy agent_engine --project <p> --region us-central1 --display_name airlock agents/pipeline`.
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
                                                               investigation (LlmAgent, gemini-2.5-flash)     |
                                                               escalation                                     |
                                                                                                              v
  gates push counters (Influx line protocol) and events (Loki)  ---->  Grafana Cloud: dashboard "Airlock gates",
  every run is one trace (OTLP over HTTP, the OTLP gateway)             annotations, incidents, alert rules, Tempo
```

One trace per run in Tempo (`airlock/tracing.py`): ADK's spans around every agent and the
investigator's calls, one `airlock.gate.<name>` span per gate with its status and cost, one
`grafana.<tool>` span per question the verdict asks. Every Loki line carries the run's `trace_id`
(the stack's derived field turns it into a link), the annotation names it, the incident links the
trace, the console's Record links it.

Inputs: a Prelinger commercial (real, public domain, `assets/real/SOURCE.md`), a Veo clip with an
injected claim and a real C2PA manifest (synthetic, labelled, `SYNTHETIC.md`), or a short upload.

ADK note: `SequentialAgent` and `ParallelAgent` are marked deprecated in google-adk 2.8.0 in favour
of `Workflow` (pytest prints the two warnings). `Workflow` is a graph node, not a `BaseAgent`, and
Agent Engine's `AdkApp` takes a `BaseAgent` as its root, so the pipeline stays on the two agents
until `Workflow` can be deployed as the root.

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
through the deployed pipeline every six hours (00:00, 06:00, 12:00, 18:00 UTC; every twelve until 2026-09-05), and pushes `airlock_daily_proof_total` with the
outcome. A failed proof is not retried into a pass (the Cloud Run job runs with `--max-retries=0`
since 2026-09-05; before that, one retry turned two proofs that met a paused Grafana Cloud into
passes, `docs/RUNS.md`): the gate that missed loses its right to PASS on its own until a calibration
catches again, and every run in between is a BLOCK "uncalibrated control".

## The console

`console/`: Next.js on Cloud Run, one screen, the light palette and type of YouTube Studio, no
animation. The clip is the stage (it plays while the gates read it) with every timestamped finding
marked on the scrubber, Frame.io style; beside it the verdict, then a segmented control: Checks (one
status line per gate, YouTube Studio's Checks step, the calibration line read from Grafana under
each, a "mute telemetry" switch inside the row to darken a gate and an "inject a fault" switch to
break it, and watch the verdict refuse either way), Findings (the thread, a click on a time seeks the
clip) and Record (the rules cited, the C2PA line, the investigator's note with the Loki lines it
cites, the annotation and the incident, and the button that resolves the incident and writes the
reviewed annotation). Two more views: the Trace (raw agent events, the investigator's tool calls)
and the Queue (Grafana's open incidents).
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
General Electric; `assets/real/eval/SOURCE.md`, fetched and cut by `scripts/fetch_assets.sh`) and
the 6 synthetic clips. The ground truth is `eval/manifest.yaml`: the expected status per gate, the
rule ids that must fire and must not fire on each asset, and for the real spots the brand on screen
and whether a person is on screen (hand-labelled from contact sheets). A percentage never travels
without its count. `eval/EVAL.md`, run of 2026-09-05 09:30 UTC on the shipped gates:

| gate | n | precision | recall | median latency | max |
|---|---|---|---|---|---|
| rights | 16 | 100% (10 of 10) | 100% (10 of 10) | 41.2 s | 87.8 s |
| claim | 5 | 100% (3 of 3) | 100% (3 of 3) | 22.0 s | 300.5 s (one call hung and the 300 s client timeout ended it as an ERROR) |
| brand | 6 | 100% (2 of 2) | 100% (2 of 2) | 16.0 s | 30.8 s |
| provenance | 16 | 100% (14 of 14) | 100% (14 of 14) | 6 ms | 86 ms |

That is the status. Scored per rule, where a forbidden rule that fires is a false positive even when
the BLOCK was right, the same run reads:

| rule | gate | n | precision | recall |
|---|---|---|---|---|
| `registry:brands:unknown` | rights | 16 | 100% (9 of 9) | 90% (9 of 10) |
| `registry:faces:no_release` | rights | 16 | 100% (7 of 7) | 100% (7 of 7) |
| `registry:explicit_content` | rights | 16 | 0% (0 of 1) | n/a (0 of 0) |
| `16 CFR 255.3` | claim | 4 | 100% (3 of 3) | 100% (3 of 3) |
| `charter:mandatory_mentions` | brand | 6 | 100% (1 of 1) | 100% (1 of 1) |
| `charter:exclusions`, `charter:palette` | brand | 5 | 100% (1 of 1) | 100% (1 of 1) |
| `airlock:provenance:manifest-required` | provenance | 16 | 100% (12 of 12) | 100% (12 of 12) |
| `airlock:provenance:signature-valid` | provenance | 4 | 100% (1 of 1) | 100% (1 of 1) |
| `airlock:provenance:signer-trusted` | provenance | 3 | 100% (1 of 1) | 100% (1 of 1) |

Brand identification, scored apart from the BLOCK: the rights gate named the brand on screen on 4 of
10 real spots (40%). The BLOCK held on all ten because the policy blocks any brand the registry does
not know; a rights desk would still need the name.

Cost at list price (`pricing.yaml`, Billing Catalog SKUs read 2026-08-29): median 0.52 USD per
30 s spot (n=16), 8.21 USD for the whole run (16 Video Intelligence minutes, 31 Gemini calls); the
Video Intelligence started minute is most of it, so an 8 s clip costs the same as a 30 s one.

What the status score hid, kept in `eval/EVAL.md` under "Surprises": Video Intelligence named the
wrong company on 6 of the 10 real spots at high confidence (a 1955 Chevrolet read as "DeLorean Motor
Company", Kodak as "Stanley Steemer"), so the gate's reason says "a logo the registry does not know"
and quotes the API's guess as a guess; on Macleans it found no logo at all and the BLOCK rests on
the ten unreleased face tracks alone (the brand rule's recall, 9 of 10); it flags the 1963 Kodak
Instamatic family party as explicit content (VERY_LIKELY on 1 frame of 28, the policy blocks at
LIKELY), a false positive a status-only score would count as a correct BLOCK, reproduced on both
runs (2026-08-29 and 2026-09-05). And the raw Veo output is not unsigned: it carries a Google-issued
C2PA manifest, which the gate blocks as an untrusted signer until the studio puts Google's
certificate on its trust list.

## What is proven, and where

`docs/RUNS.md` carries every milestone with its command, output, annotation id and incident id:
the Agent Engine run of the real clip (BLOCK on content, annotation 9, incident 6), the run with
the rights telemetry dark for 16 minutes (BLOCK, control unavailable, annotation 7), the run after
a calibration miss (BLOCK, uncalibrated control, annotation 8), and the first PASS (annotation 10).

## Tests

Five checks, no cloud call in any of them, `scripts/check.sh` runs them all and stops at the first red:

```
uv run pytest -q                                       # the rules: gates, verdict (R1, R2, instrument error, paperwork), ledger, telemetry, the MCP server
uv run ruff check .                                    # lint (E, F, B, BLE, UP at 160 columns; the ignores and their reasons are in pyproject.toml)
uv run pyright airlock agents airlock_mcp scripts      # types, basic mode
uv run python scripts/export_promql.py --check         # the console's PromQL is the verdict's
(cd console && pnpm typecheck && pnpm lint)            # the console
```

There is no CI on this repository (GitHub Actions is billing-blocked on the account, said in
`docs/RUNS.md`); `scripts/check.sh` before a commit is the gate, and the panel of 2026-09-05 caught
the one time it was skipped.

The tests cover the line-protocol formatter, the four gate decisions, the verdict rules, the
calibration ledger (one series per injected defect), the shared telemetry pushers, the settings
module, and airlock-mcp (bearer, health route, tools that leave the event loop free).

## Synthetic inputs

`SYNTHETIC.md` names every synthetic element: the Veo clip, its overlays, its self-issued signing
certificate, the calibration variants, and the fictional sommelier study in
`assets/synthetic/nimbus-test-clip-substantiated.mp4.substantiation.yaml` that lets the claim gate
be shown lifting a BLOCK. Everything else is real and named at its source.

## Layout

- `airlock/` gates, verdict rules, calibration ledger, telemetry push, the Grafana MCP toolset
- `agents/pipeline/` the ADK pipeline (the M1 spike agent, `agents/spike/`, was deleted on 2026-09-05 with its engine; `docs/RUNS.md` M1 keeps its record)
- `console/` the reviewer console (Next.js); `airlock_mcp/` the gates as MCP tools; `infra/` Google Cloud, Cloud Run and Secret Manager scripts
- `rules/` 16 CFR 255 and the ASA rulings; `charter.yaml`, `rights-registry.yaml`, `trust/`
- `scripts/` Grafana bootstrap, asset build, Agent Engine query; `tests/`; `docs/RUNS.md`

Built for Agentic Cinema (Google Cloud, Grafana Labs track), 2026-08-28 to 2026-09-09, by Dylan
Merigaud. Apache-2.0.
