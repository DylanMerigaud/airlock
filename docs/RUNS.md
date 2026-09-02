# Runs: the proof of every milestone

One block per run: the command, its output (trimmed to what proves the step), and the ids and
URLs a reader can check. The cockpit reads this file; nothing here is retyped by hand.

## M1: the Grafana loop, end to end

Status: DONE 2026-08-28.

Track decision: Grafana Labs (Airlock v2). The kill criterion switches to ClickHouse (Falsework)
only if the Agent Engine run cannot reach mcp-grafana on Cloud Run or cannot write the annotation
after the auth options are exhausted. Not triggered.

**Idea gate, run late (2026-08-29, after M1 to M4b already stood).** The plan
(`career/hackathon-evals/BUILD-AIRLOCK-V2-2026-08-28.md` in growth-cockpit) already carried the
result of this check as pre-existing evidence ("9 of 9 gates PASS") before the first commit; it was
never re-run inside this repo's own `RUNS.md`, so it is logged here for the record.
`python3 career/hackathon-evals/check.py --type idea ideas/airlock-v2.md` (growth-cockpit repo):

```
PASS  G17 zero em-dash / en-dash
PASS  G1 corpus lu  (12 gagnants cites)
PASS  G2 insight non-evident
PASS  G3 vertical etroit
PASS  G7 eligibilite copiee
PASS  G6 demo a 50 pourcent
PASS  G4 multi-agent  (6 agents)
PASS  G5 primitive sponsor
PASS  G8 track choisi
RESULTAT: PASS mecanique
```

### Auth path chosen

mcp-grafana 1.3.0 ships its own inbound bearer (`--server-auth-token`, env
`MCP_GRAFANA_SERVER_TOKEN`; unauthenticated requests get 401). Verified locally on 2026-08-28
against the darwin binary: `initialize` with the bearer answers 200, without it 401. So the Cloud
Run service is `--allow-unauthenticated` at the network level and closed at the MCP level; the
agent sends the bearer from `AIRLOCK_MCP_TOKEN` (Secret Manager on Agent Engine) through ADK's
`McpToolset(header_provider=...)`. No ID token dance, no expiry.

### Facts checked before the cloud steps (2026-08-28)

- Cloud Run deploys public Docker Hub images directly (`gcloud run deploy --image docker.io/...`),
  cached up to one hour; Google recommends an Artifact Registry remote repository for higher
  availability. Source: docs.cloud.google.com/run/docs/deploying. The spike uses the direct pull;
  the remote repository is the fallback if a pull fails on a demo day.
- Grafana Cloud Free includes IRM for 3 active users, 10k active series, 50 GB logs, 14 days
  retention. Source: grafana.com/pricing. So the verdict agent's `create_incident` has a target;
  the plan's fallback (a second annotation tagged `needs-human`) stays written in case the free
  IRM refuses the API call.

### Steps

**Step 2, project (2026-08-28 22:39 UTC).** `bash infra/gcp/bootstrap.sh` on dylanmerigaud@gmail.com:
project `airlock-agentic-cinema`, number 771466810465, billing 012DF6-79381F-D64642 linked
(`billingEnabled: true`), APIs enabled, bucket `gs://airlock-agentic-cinema-staging`, region us-central1.

**Step 6a, first Agent Engine deploy (22:41 to 22:45 UTC), before the MCP server exists.**
`uv run adk deploy agent_engine --project=airlock-agentic-cinema --region=us-central1 --display_name=airlock-spike agents/spike`
created `projects/771466810465/locations/us-central1/reasoningEngines/1949818395360755712`.
Queried over REST (`scripts/query_agent_engine.py`, `:streamQuery?alt=sse`), two events came back:

```
{"author": "airlock_spike", "text": ["spike start: mcp=http://127.0.0.1:8765/mcp airlock_pkg_importable=True"]}
{"author": "airlock_spike", "text": ["spike ERROR: ConnectionError: Failed to create MCP session: ... All connection attempts failed"]}
```

What this proves before the Grafana side exists: the deploy path, the REST streaming path, that
`extra_packages: ["../../airlock"]` makes the shared package importable on Agent Engine, and that
a failed MCP hop surfaces in the trace. The URL is the local placeholder because of the lesson below.

**Lesson (cost one redeploy).** `adk deploy agent_engine` reads a `.env` sitting in the agent
folder and overrides the `env_vars` of `.agent_engine_config.json` with its plain values, which
silently drops the Secret Manager reference. Local env now lives in `.env.local` at the repo root
(`set -a; source .env.local; set +a`), never inside an agent folder.

**Step 1, Grafana Cloud (22:50 UTC).** Free stack `narrowsubmarine1895` (auto-named by the sign-up
flow, US West, prod-us-west-0), created through Dylan's own browser on dylanmerigaud@gmail.com.
Service account `airlock-agent` (Editor) and access policy `airlock-push` (metrics and logs, read
and write). Tokens went from the browser's copy button into the macOS keychain, then
`bash infra/gcp/secrets.sh` loaded them into Secret Manager: `grafana-sa-token`,
`grafana-influx-token`, `airlock-mcp-token` (64 hex chars, generated). Coordinates in `.env.example`.
Dashboard: `scripts/grafana_bootstrap.py` created `airlock-gates`
(https://narrowsubmarine1895.grafana.net/d/airlock-gates/airlock-gates), Prometheus datasource
uid `grafanacloud-prom`.

**Step 3, mcp-grafana on Cloud Run (22:52 to 22:56 UTC).** `GRAFANA_URL=... bash infra/mcp-grafana/deploy.sh`:
service `airlock-mcp-grafana`, image `docker.io/grafana/mcp-grafana:1.3.0`, revision 00003,
URL https://airlock-mcp-grafana-771466810465.us-central1.run.app/mcp (the legacy
`...-3pyftkcubq-uc.a.run.app` form is also allowed). Probed from this machine with `initialize`:

```
with bearer: 200
without bearer: 401
deterministic host with bearer (before both hosts were allowed): 403, then 200 on revision 3
```

**Step 4, one counter through the Influx endpoint (22:55 UTC).** `scripts/with_env.sh uv run python scripts/push_spike_metric.py`:

```
{"http_status": 204, "line": "airlock_gate,gate=spike errors_total=0i,last_success_ts=1787957724i,runs_total=1i 1787957724385039000"}
```

Read back through `POST /api/ds/query` on `grafanacloud-prom` with
`sum(sum_over_time(airlock_gate_runs_total{gate="spike"}[24h]))`: one frame, value `1`.

**Step 5 and 6, local run (22:57 UTC).** `AIRLOCK_MCP_URL=https://airlock-mcp-grafana-771466810465.us-central1.run.app/mcp scripts/with_env.sh uv run adk run agents/spike "run the spike"`:

```
[airlock_spike]: spike start: mcp=https://airlock-mcp-grafana-771466810465.us-central1.run.app/mcp airlock_pkg_importable=True
[airlock_spike]: mcp tools reachable: ['create_annotation', 'list_datasources', 'query_prometheus']
[airlock_spike]: prometheus datasource uid: grafanacloud-prom
[airlock_spike]: promql sum(sum_over_time(airlock_gate_runs_total{gate="spike"}[24h])) => {"data":[{"metric":{},"value":[1787957843.958,"1"]}]}
[airlock_spike]: annotation created: {"Payload":{"id":1,"message":"Annotation added"}}
[airlock_spike]: spike done in 4512 ms
```

**Step 6, Agent Engine run (22:57 to 23:00 UTC).** Redeploy with the real MCP URL in
`.agent_engine_config.json` (`adk deploy agent_engine ... --agent_engine_id=1949818395360755712`,
2 min 21 s), then `uv run python scripts/query_agent_engine.py projects/771466810465/locations/us-central1/reasoningEngines/1949818395360755712 "run the spike"`:

```
spike start: mcp=https://airlock-mcp-grafana-771466810465.us-central1.run.app/mcp airlock_pkg_importable=True
mcp tools reachable: ['create_annotation', 'list_datasources', 'query_prometheus']
prometheus datasource uid: grafanacloud-prom
promql sum(sum_over_time(airlock_gate_runs_total{gate="spike"}[24h])) => {"data":[{"metric":{},"value":[1787957999.088,"1"]}]}
annotation created: {"Payload":{"id":2,"message":"Annotation added"}}
spike done in 2357 ms
```

Both annotations read back through `GET /api/annotations?dashboardUID=airlock-gates&tags=airlock`:

```
{"id": 2, "dashboardUID": "airlock-gates", "time": 1787957999440, "text": "spike ok: sum(sum_over_time(airlock_gate_runs_total{gate=\"spike\"}[24h])) answered from agent-engine", "tags": ["airlock", "spike", "agent-engine"]}
{"id": 1, "dashboardUID": "airlock-gates", "time": 1787957844174, "text": "spike ok: sum(sum_over_time(airlock_gate_runs_total{gate=\"spike\"}[24h])) answered from local", "tags": ["airlock", "spike", "local"]}
```

### M1 done (2026-08-28 23:01 UTC)

Local run: annotation 1 (tag `local`). Agent Engine run: annotation 2 (tag `agent-engine`). The
PromQL answer is in both traces. Kill criterion not triggered; track stays Grafana Labs.

## M2: the four gates on real inputs, locally

Status: DONE 2026-08-28 (23:23 UTC).

### Inputs

- Real: `assets/real/CrestToothpa-18-48.mp4`, seconds 18 to 48 of the Prelinger "Crest Toothpaste
  Commercial 1" (public domain, stream-copied, sha256 in `assets/real/SOURCE.md`). The full 60 s
  film costs the Video Intelligence API about 4 minutes; the excerpt about 1 to 2.
- Synthetic, labelled: `assets/synthetic/nimbus-test-clip.mp4`, 8 s from Veo 3.1 on Vertex AI plus
  ffmpeg overlays, signed with c2patool and a self-issued test certificate (`SYNTHETIC.md`).
- Rules: `rules/ftc-16-cfr-255.md` (eCFR, 2026-08-01), `rules/asa-rulings.md` (A26-1337640,
  G26-1344778, both 2026-08-26). Charter: `charter.yaml`. Registry: `rights-registry.yaml`.

### Gates and their sources of truth

| gate | source of truth | decision |
|---|---|---|
| rights | Video Intelligence (logos, faces, text, explicit) against the registry | an identifiable element the registry does not clear blocks |
| claim | gemini-2.5-pro extracts claims with timestamps; 16 CFR 255 and the ASA rulings map each kind | a regulated claim with no substantiation on file blocks |
| brand | gemini-2.5-flash reads the asset against the charter | mandatory mention, exclusions, tone, palette, typography |
| provenance | c2pa-python against `trust/trust-anchors.pem` | no manifest, invalid signature or untrusted signer blocks |

Every decision is a plain function under pytest (`tests/`, 36 tests); the models only read.

### Verification, twice in a row

`scripts/with_env.sh uv run python -m airlock.run assets/real/CrestToothpa-18-48.mp4 --gcs-uri gs://airlock-agentic-cinema-assets/real/CrestToothpa-18-48.mp4`

```
run 1 (23:15 UTC)                                  run 2 (23:19 UTC)
rights      BLOCK   58697 ms  brand Crest (not_cleared, logo at 16.12s, 0.853); 7 face tracks, no release
claim       BLOCK   35910 ms  9 regulated claims, first "my side had 21% fewer cavities with Crest." (16 CFR 255.2(a))
brand       BLOCK   24244 ms  Nimbus wordmark never seen; health claim, comparison, children
provenance  BLOCK      15 ms  no C2PA manifest in the asset
                                                   rights BLOCK 119790 ms (same reasons), claim BLOCK 38817 ms (10 claims),
                                                   brand BLOCK 21527 ms, provenance BLOCK 16 ms
```

`scripts/with_env.sh uv run python -m airlock.run assets/synthetic/nimbus-test-clip.mp4 --gcs-uri gs://airlock-agentic-cinema-assets/synthetic/nimbus-test-clip.mp4`

```
run 2 (23:17 UTC)                                  run 3 (23:21 UTC)
rights      PASS    90208 ms  cleared brand(s): Nimbus; no unreleased face, no explicit content      33700 ms, same
claim       BLOCK   17853 ms  "Recommended by 9 out of 10 sommeliers." (expert_endorsement, 16 CFR 255.3)   19305 ms, same
brand       PASS    12750 ms  Nimbus wordmark seen, palette, tone and exclusions respected          56827 ms, same
provenance  PASS       49 ms  C2PA manifest verified and trusted; signed by Airlock (hackathon test)   23 ms, same
```

(Run 1 of the synthetic clip, 23:15 UTC, had provenance BLOCK with `signingCredential.untrusted`:
that is what led to the trust list; see below.)

### What the plan did not know

- Gemini 2.5 flash mis-scales video timestamps (it answered 0.24 for 14 s on the 60 s probe);
  2.5 pro gets them right. Pro extracts claims, flash reads the charter, as the plan assigned.
- c2pa-rs 0.90 files `signingCredential.untrusted` under `failure` for a self-issued signer while
  the state stays `Valid`. The gate now verifies against a studio trust list
  (`trust/trust-anchors.pem`, the signer's public certificate on the reader's allowed list) and
  the state becomes `Trusted`. Unknown signer stays a BLOCK with its own rule id.
- Video Intelligence latency is the wild card: 30 s to 120 s on the same 30 s input, 598 s when
  three jobs ran at once. The rights gate has a feature set knob and a timeout that turns into an
  ERROR the verdict treats as an instrument failure. The gates run in parallel inside the pipeline.
- The agent folder cannot be named `airlock`: ADK imports the agent folder as a top-level module,
  which shadows the library package. It is `agents/pipeline`.
- `adk deploy` reads a `.env` in the agent folder over the config's Secret Manager refs (M1).

## M3: the verdict agent, the calibration ledger, the loop closed

Status: DONE 2026-08-28 (23:51 UTC).

### Shape

`agents/pipeline`: `SequentialAgent(airlock) = ParallelAgent(gates: rights, claim, brand, provenance)
then verdict then escalation`. The gates are `BaseAgent`s around the plain gate functions, run in
threads so the four are really parallel (measured: the first version serialized them because the
gate functions block the event loop). The verdict is a `BaseAgent` that asks Grafana through
mcp-grafana (list_datasources, then per gate the PromQL questions of `airlock/verdict.py`),
applies the rules, writes the annotation. The escalation opens the incident when the verdict says
a human is needed, or falls back to a `needs-human` annotation when the Incident API refuses.
The input is a GCS URI, or `{"gcs_uri": ..., "asset_id": ..., "mute": ["rights"]}` where `mute`
silences a gate's telemetry (a judge's "disable a gate" action).

Deviation from the plan, and why: the plan said three PromQL questions per gate; there are four,
the third being asked twice (catches over 7 days, and whether the last calibration run caught its
defect), because verification C ("calibrate with the claim defect removed, rerun, claim is
ADVISORY") cannot be shown with a 7-day count that stays positive.

### Calibration ledger (`python -m airlock.calibrate`, 23:21 to 23:28 UTC)

```
rights      CAUGHT  298291 ms  real trademark not cleared, faces without release  ->  BLOCK ['registry:brands:not_cleared', 'registry:faces:no_release']
claim       MISSED    1188 ms  expert endorsement with no substantiation  ->  ERROR []      (a bug on GCS-only assets, fixed; rerun below)
brand       CAUGHT   27906 ms  forbidden red banner and urgency copy  ->  BLOCK ['charter:exclusions', 'charter:palette']
provenance  CAUGHT      55 ms  manifest stripped  ->  BLOCK ['airlock:provenance:manifest-required']
provenance  CAUGHT      68 ms  signed copy with one byte flipped  ->  BLOCK ['airlock:provenance:signature-valid']
claim       CAUGHT   16455 ms  expert endorsement with no substantiation  ->  BLOCK ['16 CFR 255.3', 'ASA A26-1337640 (CAP 3.7)']   (rerun 23:27)
```

The miss was pushed as a miss: the ledger is what happened, not what was intended.

### Local pipeline runs (`scripts/with_env.sh uv run adk run agents/pipeline "gs://.../synthetic/nimbus-test-clip.mp4"`)

Run 3 (23:27 UTC), with a race in the Gemini client construction that made the claim gate fail:

```
rights PASS 31077 ms | brand PASS 15397 ms | provenance PASS 6529 ms | claim ERROR 1021 ms (client closed)
verdict: grafana rights healthy 9 s ago, calibrated | claim error rate 30% over 15m | brand healthy | provenance healthy, 2 catches
VERDICT BLOCK (instrument error) needs_human True, annotation 3
escalation: create_incident refused by the stack: "Counter.Insert ... foreign key constraint fails (grafana_incident.Counters)"
```

Run 4 (23:30 UTC), race fixed:

```
provenance PASS 5428 ms | brand PASS 14445 ms | claim BLOCK 25619 ms | rights PASS 46593 ms   (parallel, 66 s wall)
verdict: rights healthy 10 s ago | claim error rate 33% over 15m (the run-3 error, honestly still in the window) | brand healthy | provenance healthy
VERDICT BLOCK (content) needs_human False, annotation 4: "Recommended by 9 out of 10 sommeliers." (expert_endorsement, 16 CFR 255.3)
escalation: no human needed
```

The Incident refusal is the signature of an Incident app never opened on the stack; it is being
initialized through the UI, and the fallback annotation is in the code either way.

Agent Engine: `reasoningEngines/1737023312967499776` (display name `airlock`), first deploy 23:32 UTC.
Public dashboard for the judges: https://narrowsubmarine1895.grafana.net/public-dashboards/97860661238c4536a743e0d858aef845

### Local run 5, the loop closed (23:39 to 23:40 UTC)

`scripts/with_env.sh uv run adk run agents/pipeline '{"gcs_uri": "gs://airlock-agentic-cinema-assets/real/CrestToothpa-18-48.mp4", "asset_id": "CrestToothpa-18-48", "mute": ["rights"]}'`

```
provenance BLOCK  4617 ms | brand BLOCK 13338 ms | claim BLOCK 41208 ms | rights BLOCK 65304 ms (telemetry muted)
verdict: rights healthy, last success 533 s ago, 1 catch | claim error rate 40% over 15m, 1 catch | brand healthy, 1 catch | provenance healthy, 2 catches
VERDICT BLOCK (content) needs_human True, annotation 5
  rights: BLOCK, brand Crest (not_cleared, logo at 16.12s, confidence 0.853): Real registered trademark. No licence on file for this asset.
  claim: BLOCK, 9 regulated claim(s) with no substantiation on file; first at 7.5s: "my side had 21% fewer cavities with Crest." (consumer_testimonial, 16 CFR 255.2(a))
  brand: BLOCK, mandatory mention missing: the Nimbus wordmark is never seen
  provenance: BLOCK, no C2PA manifest in the asset
  a human can lift this BLOCK by supplying the missing substantiation, licence or release
escalation: INCIDENT 2 opened in Grafana Incident: "Airlock needs a human: content on CrestToothpa-18-48" (drill, Minor, label airlock=content)
```

Grafana Incident had to be opened once from the UI (app slug `grafana-irm-app`; a drill declared and
resolved) before `create_incident` stopped answering the foreign-key error. The fallback stays in
the code for a stack that has not been initialized.

Redeploy of `reasoningEngines/1737023312967499776` with this code: 23:38 to 23:40 UTC.

### Agent Engine run 1, the clean clip with rights muted (23:41:44 to 23:42:33 UTC, 48.5 s)

`uv run python scripts/query_agent_engine.py projects/771466810465/locations/us-central1/reasoningEngines/1737023312967499776 '{"gcs_uri": "gs://airlock-agentic-cinema-assets/calibration/nimbus-clean-clip.mp4", "asset_id": "nimbus-clean-clip", "mute": ["rights"]}'`

```
[   3.3s] rights_gate      running  rights  (telemetry muted)
[   5.9s] provenance_gate  PASS      684 ms  C2PA manifest verified and trusted; signed by Airlock (hackathon test)
[  14.6s] brand_gate       PASS     9543 ms  Nimbus wordmark seen, palette, tone and exclusions respected
[  18.4s] claim_gate       PASS    13541 ms  no regulated claim without substantiation (1 claim(s) read, 1 advisory)
[  39.5s] rights_gate      PASS    35976 ms  cleared brand(s): Nimbus; no unreleased face, no explicit content
[  41.5s] verdict  grafana rights      healthy, last success 651 s ago; caught 1 injected defect(s) in 7d
[  42.7s] verdict  grafana claim       error rate 20% over 15m; caught 1 injected defect(s) in 7d
[  43.6s] verdict  grafana brand       healthy, last success 30 s ago; caught 1 injected defect(s) in 7d
[  44.6s] verdict  grafana provenance  healthy, last success 40 s ago; caught 2 injected defect(s) in 7d
[  45.6s] verdict  VERDICT BLOCK (control unavailable) needs_human=True annotation=6
                   claim: control unavailable (error rate 20% over 15m)
[  48.2s] escalation INCIDENT 3
```

Four PASS and still no PASS verdict: the claim gate's errors of 23:27 and 23:30 UTC (the client race,
fixed since) were still inside the 15-minute window, and R1 does not care that the gate just
succeeded. That is the rule working on real telemetry, not on a staged failure.

### Verification B: rights telemetry dark for 16 minutes, rerun from Agent Engine (23:47:13 UTC, 42.8 s)

Same command as run 1 (`mute: ["rights"]`), with the last rights success at 23:31 UTC:

```
[   4.1s] provenance_gate  PASS      162 ms
[  17.5s] claim_gate       PASS    13831 ms
[  32.8s] brand_gate       PASS    29027 ms
[  34.4s] rights_gate      PASS    32105 ms  cleared brand(s): Nimbus; no unreleased face, no explicit content
[  36.5s] verdict  grafana rights      last success 975 s ago, older than 900 s; caught 1 injected defect(s) in 7d
[  37.5s] verdict  grafana claim       healthy, last success 21 s ago
[  38.3s] verdict  grafana brand       healthy, last success 7 s ago
[  39.3s] verdict  grafana provenance  healthy, last success 36 s ago
[  40.2s] verdict  VERDICT BLOCK (control unavailable) needs_human=True annotation=7
                   rights: control unavailable (last success 975 s ago, older than 900 s)
[  42.7s] escalation INCIDENT 4
```

The rights gate itself reported PASS in 32 s; the verdict did not take its word for it.

### Verification C: calibrate with the claim defect removed, rerun from Agent Engine (23:48 to 23:49 UTC)

`scripts/with_env.sh uv run python -m airlock.calibrate --gate claim --defect-removed`

```
claim       MISSED   15330 ms  expert endorsement with no substantiation (defect removed)  ->  PASS ['16 CFR 255.1']
{"defects": 1, "caught": 0, "missed": 1, "elapsed_s": 20.1, "pushed": true}
```

Then the clean clip, unmuted (`{"gcs_uri": "gs://.../calibration/nimbus-clean-clip.mp4", "asset_id": "nimbus-clean-clip"}`, 54.5 s):

```
[   4.2s] provenance_gate  PASS      170 ms
[  13.2s] brand_gate       PASS     9309 ms
[  16.4s] claim_gate       PASS    12784 ms
[  46.2s] rights_gate      PASS    42627 ms
[  48.1s] verdict  grafana rights      healthy, last success 2 s ago; caught 1 injected defect(s) in 7d
[  49.1s] verdict  grafana claim       healthy, last success 23 s ago; last calibration run MISSED its defect (1 caught earlier in 7d)
[  50.0s] verdict  grafana brand       healthy, last success 35 s ago; caught 1 injected defect(s) in 7d
[  51.0s] verdict  grafana provenance  healthy, last success 44 s ago; caught 2 injected defect(s) in 7d
[  51.9s] verdict  VERDICT BLOCK (uncalibrated control) needs_human=True annotation=8
                   claim: PASS is advisory only, last calibration run MISSED its defect (1 caught earlier in 7d)
[  54.5s] escalation INCIDENT 5
```

### Verification A: the Prelinger excerpt from Agent Engine (23:48:50 UTC, 119.4 s)

`uv run python scripts/query_agent_engine.py projects/771466810465/locations/us-central1/reasoningEngines/1737023312967499776 'gs://airlock-agentic-cinema-assets/real/CrestToothpa-18-48.mp4'`

```
[   3.9s] provenance_gate  BLOCK     117 ms  no C2PA manifest in the asset
[  12.2s] brand_gate       BLOCK    8501 ms  mandatory mention missing: the Nimbus wordmark is never seen
[  23.4s] claim_gate       BLOCK   20003 ms  8 regulated claim(s) with no substantiation on file; first at 7.1s: "my side had 21% fewer cavities with Crest." (16 CFR 255.2(a))
[ 111.4s] rights_gate      BLOCK  108158 ms  brand Crest (not_cleared, logo at 16.12s, confidence 0.853): Real registered trademark. No licence on file for this asset.
[ 113.2s] verdict  grafana rights      healthy, last success 3 s ago; caught 1 injected defect(s) in 7d
[ 114.4s] verdict  grafana claim       healthy, last success 1 s ago; caught 2 injected defect(s) in 7d
[ 115.3s] verdict  grafana brand       healthy, last success 8 s ago; caught 1 injected defect(s) in 7d
[ 116.2s] verdict  grafana provenance  healthy, last success 17 s ago; caught 2 injected defect(s) in 7d
[ 117.1s] verdict  VERDICT BLOCK (content) needs_human=True annotation=9
                   rights: BLOCK, brand Crest (not_cleared, logo at 16.12s, confidence 0.853) ...
                   claim: BLOCK, 8 regulated claim(s) with no substantiation on file ...
                   brand: BLOCK, mandatory mention missing: the Nimbus wordmark is never seen
                   provenance: BLOCK, no C2PA manifest in the asset
                   a human can lift this BLOCK by supplying the missing substantiation, licence or release
[ 119.3s] escalation INCIDENT 6
```

The rights gate took 108 s because three Video Intelligence jobs ran at once (runs A, C and D
overlapped); alone it takes 30 to 60 s on this 30 s excerpt.

### M3 done (2026-08-28 23:51 UTC)

| verification | run | verdict | annotation | incident |
|---|---|---|---|---|
| A: Prelinger clip from Agent Engine, three PromQL answers per gate in the trace | 23:48:50 | BLOCK, content | 9 | 6 |
| B: rights pushes dark 16 min, rerun | 23:47:13 | BLOCK, control unavailable | 7 | 4 |
| C: calibrate with the claim defect removed, rerun | 23:48:47 | BLOCK, uncalibrated control | 8 | 5 |

Every verdict is an annotation on https://narrowsubmarine1895.grafana.net/d/airlock-gates/airlock-gates
(public: https://narrowsubmarine1895.grafana.net/public-dashboards/97860661238c4536a743e0d858aef845)
and every needs-human BLOCK is a drill incident in Grafana IRM on the same stack.

### Run D: the first PASS (23:50:26 UTC, 48.0 s)

After `calibrate --gate claim` caught its defect again (`claim CAUGHT 15627 ms`), the clean clip
unmuted from Agent Engine:

```
[   4.0s] provenance_gate  PASS      124 ms
[  12.0s] brand_gate       PASS     8350 ms
[  18.2s] claim_gate       PASS    14680 ms
[  42.2s] rights_gate      PASS    38787 ms
[  44.0s] verdict  grafana rights      healthy, last success 2 s ago; caught 1 injected defect(s) in 7d
[  44.9s] verdict  grafana claim       healthy, last success 27 s ago; caught 2 injected defect(s) in 7d
[  45.7s] verdict  grafana brand       healthy, last success 34 s ago; caught 1 injected defect(s) in 7d
[  46.7s] verdict  grafana provenance  healthy, last success 43 s ago; caught 2 injected defect(s) in 7d
[  47.8s] verdict  VERDICT PASS (content) needs_human=False annotation=10
                   all 4 gates PASS, healthy and calibrated
[  48.0s] escalation no human needed: verdict PASS on content
```

The only PASS of the day, and it took four calibrated, healthy gates and a clean signed asset to
get it. Annotations 1 to 10 and incidents 2 to 6 are the day's ledger on the stack.

## M4: the console on Cloud Run

Status: in progress (started 2026-08-28 23:35 UTC).

### Build

`console/`: Next.js 15, TypeScript, Tailwind, shadcn-style components restyled (dark, one amber
accent, Sora and IBM Plex Mono). One page: top bar (wordmark, asset picker with the two demo
assets and an upload, Run button, environment badge), the pipeline column (five gate cards with
source of truth, status chip and calibration badge from `/api/health`, plus the escalation row),
the event timeline (one row per agent event, raw JSON expandable, "open in Grafana" on the verdict
row with the annotation id), the verdict card (PASS or BLOCK, motive, reasons, rule chips grouped
by authority, the C2PA line, the human-review button), stat tiles from `/api/stats`, the spec
strip. Second tab: the BLOCK queue with re-run. Six states designed: idle, running (step named),
passed, blocked, gate degraded (amber), instrument error (red). Mock mode replays real fixtures
(`console/fixtures/`, recorded from the pipeline runs of this file) so the app builds and runs
without any credential. Verified before deploy: `pnpm build`, `pnpm lint`, `pnpm typecheck` clean,
SSE relay smoke-tested in mock mode, no server left running.

### Deploy (2026-08-29 00:08 to 00:14 UTC)

First `gcloud run deploy --source console` failed in Cloud Build: `corepack enable` resolved pnpm
10, whose `minimumReleaseAge` policy rejected three lockfile entries published the same day
(`@jridgewell/sourcemap-codec@1.6.0`, `fastq@1.20.2`, `string.prototype.matchall@4.1.0`). Fixed by
pinning `"packageManager": "pnpm@9.15.0"` (the local version) and deploying from a clean
`git archive` snapshot of the committed console.

Second deploy: service `airlock-console`, revision `airlock-console-00001-sm4`,
URL https://airlock-console-771466810465.us-central1.run.app (also
https://airlock-console-3pyftkcubq-uc.a.run.app). Runtime identity: the project's compute service
account with `aiplatform.user`, `storage.objectAdmin` and `secretmanager.secretAccessor`; the
Grafana token from Secret Manager. Probed at 00:14 UTC:

```
GET /            200 in 1.9 s
GET /api/health  {"ok":true,"mock":false, gates: rights healthy (390 s since success, 1 catch), claim healthy, brand healthy, provenance healthy}
GET /api/stats   {"ok":true,"mock":false,"checked_7d":9,"passed_7d":2,"blocked_7d":7,"incidents_7d":6,"gates_calibrated":4,"gates_total":4}
```

### First run through the hosted console (2026-08-29 00:14:22 UTC, 56 s)

`curl -sN -X POST https://airlock-console-771466810465.us-central1.run.app/api/run -d '{"asset":"nimbus"}'`, the SSE relay decoded:

```
   3.3s provenance_gate  PASS      204 ms
  16.4s brand_gate       PASS    13409 ms
  17.3s claim_gate       BLOCK   14530 ms
  46.3s rights_gate      PASS    43652 ms
  48.7s verdict  grafana rights: healthy, last success 3 s ago; caught 1 injected defect(s) in 7d
  49.6s verdict  grafana claim: healthy, last success 33 s ago; caught 2 injected defect(s) in 7d
  50.6s verdict  grafana brand: healthy, last success 35 s ago; caught 1 injected defect(s) in 7d
  51.6s verdict  grafana provenance: healthy, last success 49 s ago; caught 2 injected defect(s) in 7d
  52.5s verdict  VERDICT BLOCK (content) needs_human=True annotation=12
  55.0s escalation opened=True incident=7
```

Cloud Run (console, ADC of the runtime account) to Agent Engine to the gates to mcp-grafana on
Cloud Run to Grafana Cloud and back to the browser, with no credential outside Secret Manager.

### Revision 2 and the mute path through the hosted console (2026-08-29 00:25 UTC)

Revision `airlock-console-00002-qnm` adds the third asset (the clean signed clip, the one that
PASSes), a per-gate "mute telemetry" switch (the judge's "disable a gate" action: the run message
becomes `{"gcs_uri", "asset_id", "mute": ["rights"]}`) and the PASS state exercised on a recorded
run (annotation 11). `curl -sN -X POST .../api/run -d '{"asset":"nimbus","mute":["rights"]}'`:

```
   1.0s rights_gate      running MUTED
   3.0s provenance_gate  PASS      146 ms
  15.8s brand_gate       PASS    13065 ms
  17.1s claim_gate       BLOCK   14072 ms
  72.6s rights_gate      PASS    71466 ms  (telemetry muted)
  74.9s verdict  grafana rights: healthy, last success 715 s ago   (the previous run's push; under 900 s)
  78.8s verdict  VERDICT BLOCK (content) annotation=13
  81.2s escalation opened=True incident=8
```

### Cold-user test (2026-08-29 00:26 to 00:34 UTC)

A fresh browser tab on https://airlock-console-771466810465.us-central1.run.app, no login, driven by
someone who had not seen the app (a browser agent on its own tab; the closest available to a person
other than Dylan, and said as such):

- Idle: the three assets, the environment badge "Vertex AI Agent Engine, us-central1" (no MOCK), the
  calibration line of every gate read live from Grafana.
- Crest run: 72 s from click to verdict. BLOCK, motive content, needs a human. Reasons in order:
  the Crest logo not cleared (16.12 s, 0.853), 9 regulated claims (first "my side had 21% fewer
  cavities with Crest.", 16 CFR 255.2(a)), the Nimbus wordmark missing, no C2PA manifest. Rule chips
  grouped by authority. Annotation 14, incident 9. While running: the step named on each card
  ("Video Intelligence: logos, faces, text", "gemini-2.5-pro reading claims"), no bare spinner.
- "Open in Grafana": the public dashboard, live tiles (6 BLOCK content, 2 PASS, 2 control
  unavailable, 1 instrument error, 1 uncalibrated at that moment).
- Clean clip run: 35 s. PASS, "all 4 gates PASS, healthy and calibrated", C2PA trusted signer named.
  Annotation 15, no incident.
- Stat tiles: 13 checked, 10 blocked, 3 passed, 4 of 4 gates calibrated, 9 incidents (7 days).
- BLOCK queue: the Crest run, with re-run.
- Visible errors: none (page text and `[role=alert]` probed at every state).

Screenshots: `docs/img/console-crest-block-2026-08-29.png`, `docs/img/console-clean-pass-2026-08-29.png`.

### M4 done (2026-08-29, ahead of the 2026-09-03 demo date)

The demo runs end to end on the URL: two assets, two correct and different verdicts, the Grafana
link, the incident. Accessibility audit: see the Lighthouse block below.

Cut list, what is NOT built and will not be for the submission:
- no multi-tenant, no authentication: one console, one stack, one registry, one charter
- no async queue: a run is one SSE stream, the browser stays on the page
- one video format (mp4), 30 s and 50 MB at most per upload
- one console view plus the BLOCK queue tab; no rights-registry or charter editor
- the calibration ledger runs on demand (`python -m airlock.calibrate`), not on a schedule
  (superseded on 2026-09-02 by M8: a Cloud Run job re-proves every gate every 12 hours)
- the rights registry and the charter are YAML files in the repo

### Revision 3 (2026-08-29 00:41 UTC)

`airlock-console-00003-4sv`: the verdict card and the spec strip show the run's wall time (the
`done` frame's `elapsed_ms`) instead of the verdict agent's own hop. Page 200 in 1.9 s.

### Lighthouse on the hosted URL (2026-08-29 00:36 UTC, desktop, navigation mode)

Accessibility 95, best practices 100, SEO 100 (54 audits passed, 2 failed in the agentic-browsing
category, which is not a submission criterion). The bar in the plan was accessibility above 90.

## M4b: airlock-mcp, the gates as tools

Status: DONE 2026-08-29 (00:35 UTC).

### Build

`airlock_mcp/server.py`: `FastMCP("airlock")` over the streamable HTTP transport, mounted in a
Starlette app behind a plain ASGI bearer middleware (`AIRLOCK_MCP_SERVER_TOKEN`; everything but
`GET /healthz` needs it). Seven tools: `check_rights`, `check_claim`, `check_brand`,
`check_provenance` (each runs its gate through `airlock.gates.base.run_gate`, so Grafana counters
and events flow the same as a pipeline run), `check_all` (the four in a `ThreadPoolExecutor`, plus
`wall_ms`), `verdict_rules` (the `airlock.verdict` docstring plus the rights gate's PromQL
questions) and `list_rules` (the FTC section headings and the two ASA references, read off
`rules/`). `Dockerfile.mcp` at the repo root; `infra/airlock-mcp/deploy.sh`;
`scripts/airlock_mcp_client.py`; `tests/test_airlock_mcp.py` (5 tests, no model, no cloud).
`pyproject.toml`: `airlock_mcp` added to `[tool.hatch.build.targets.wheel] packages`, `starlette`
and `uvicorn` promoted from transitive (already pulled in by `mcp`) to direct dependencies since
`airlock_mcp/server.py` imports them itself; `uv lock` re-resolved with no version changes.

### A bug caught before the deploy counted as done

First deploy answered every `/mcp` call with `HTTP 421 Invalid Host header`, curl showing the
literal body `Invalid Host header`. Cause: `FastMCP`'s default `transport_security` is DNS-rebinding
protection with `allowed_hosts` limited to `127.0.0.1` and `localhost`, meant for a dev server
reachable from a browser; Cloud Run's own hostname never matches it. Fixed by constructing
`FastMCP("airlock", transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))`,
since the bearer middleware is this server's real access control. Rebuilt, redeployed
(revision `airlock-mcp-00002-89h`), confirmed against the live URL below.

### Verification 1: the suite

`uv run pytest -q`

```
46 passed, 2 warnings in 0.88s
```

(41 before this milestone, 5 added in `tests/test_airlock_mcp.py`: the tool list, `create_app()`
refusing without a token, `/mcp` answering 401 with no bearer and with the wrong one, `/healthz`
open and listing the seven tools.)

### Verification 2: local, token from the keychain, telemetry through `with_env.sh`

```
TOKEN="$(security find-generic-password -s airlock-mcp-server-token -a dylanmerigaud -w)"
AIRLOCK_MCP_SERVER_TOKEN="$TOKEN" scripts/with_env.sh uv run python -m airlock_mcp.server &
```

```
curl http://127.0.0.1:8080/healthz
  200  {"ok":true,"tools":["check_rights","check_claim","check_brand","check_provenance","check_all","verdict_rules","list_rules"]}
curl -X POST http://127.0.0.1:8080/mcp (no bearer)
  401  {"error":"unauthorized"}
```

`uv run python scripts/airlock_mcp_client.py --local`:

```
tools: ['check_rights', 'check_claim', 'check_brand', 'check_provenance', 'check_all', 'verdict_rules', 'list_rules']
check_provenance(gs://airlock-agentic-cinema-assets/calibration/nimbus-clean-clip.mp4) -> PASS in 8240 ms (as expected)
  reason: C2PA manifest verified and trusted; signed by Airlock (hackathon test); created by airlock-synthetic-asset
check_provenance(gs://airlock-agentic-cinema-assets/real/CrestToothpa-18-48.mp4) -> BLOCK in 6857 ms (as expected)
  reason: no C2PA manifest in the asset
```

Server killed, `pgrep -f airlock_mcp` empty afterward.

### Verification 3: deploy and the deployed URL

`bash infra/airlock-mcp/deploy.sh`: secret `airlock-mcp-server-token` generated (keychain, then
Secret Manager, 64 hex chars, never printed), Artifact Registry repository `airlock` created in
`us-central1`, image built with `gcloud builds submit --tag
us-central1-docker.pkg.dev/airlock-agentic-cinema/airlock/airlock-mcp:latest` from a temporary
build context (`Dockerfile.mcp` copied in as `Dockerfile`, the tracked file keeps its name),
deployed as Cloud Run service `airlock-mcp`.

```
Service [airlock-mcp] revision [airlock-mcp-00002-89h] has been deployed and is serving 100 percent of traffic.
Service URL: https://airlock-mcp-771466810465.us-central1.run.app
```

`uv run python scripts/airlock_mcp_client.py` (default URL):

```
connecting to https://airlock-mcp-771466810465.us-central1.run.app/mcp
tools: ['check_rights', 'check_claim', 'check_brand', 'check_provenance', 'check_all', 'verdict_rules', 'list_rules']
check_provenance(gs://airlock-agentic-cinema-assets/calibration/nimbus-clean-clip.mp4) -> PASS in 4068 ms (as expected)
  reason: C2PA manifest verified and trusted; signed by Airlock (hackathon test); created by airlock-synthetic-asset
check_provenance(gs://airlock-agentic-cinema-assets/real/CrestToothpa-18-48.mp4) -> BLOCK in 1823 ms (as expected)
  reason: no C2PA manifest in the asset

real  8.7s wall (the whole script: connect, initialize, two tool calls, one Grafana push each)
```

Cloud Run logs for that run show the Influx and Loki pushes going through:

```
POST https://prometheus-prod-67-prod-us-west-0.grafana.net/api/v1/push/influx/write "HTTP/1.1 204 No Content"
POST https://logs-prod-021.grafana.net/loki/api/v1/push "HTTP/1.1 204 No Content"
```

### A platform limit found, not a bug fixed

`GET /healthz` on the deployed URL answers a Google-branded `404` that never reaches the
container (zero log lines for it, confirmed by `gcloud run services logs read`, while every other
path and method does show up). Cloud Run's frontend reserves `/healthz` for its own internal
probing and answers it before the request reaches the app; this reproduces a documented,
externally reported Cloud Run behavior, not a defect in this server. `/healthz` stays at that path
in the code, exactly as specified, since it is open and correct everywhere else (local `uv run`,
local `docker run`, the test suite's `TestClient`); a liveness probe against the deployed service
should hit `/mcp` instead (401 without a bearer still proves the service answers). Documented in
`docs/AIRLOCK-MCP.md`.

### M4b done (2026-08-29 00:35 UTC)

URL: `https://airlock-mcp-771466810465.us-central1.run.app` (`/mcp` for tools, `/healthz` locally
and in `docker run` only, not on this Cloud Run host). Revision `airlock-mcp-00002-89h`. 46 of 46
tests green, both demo assets answer through the deployed tool exactly as the pipeline does.

## M5: the video

Status: in progress (started 2026-08-29 01:00 UTC).

Script v2 (`docs/VIDEO-SCRIPT.md`): three runs in one take, one decision shown three ways (the real
film blocked on its content; a clean signed asset blocked because a control went dark; the same
asset passed once the control is back). The staleness rule cannot be shown after an unmuted run in
the same take, which is why the muted run comes before the PASS. Voice: Dylan's for the final;
drafts use Google Cloud Text-to-Speech and say so in their file name.

Timing measured 2026-08-29 01:03 UTC on a 15 s Crest excerpt: rights 47 s, claim 25 s. The rights
gate does not get faster with a shorter input (30 s excerpt: 43 to 72 s), so the 30 s excerpt stays
and each run is 45 to 75 s. The draft's cue log, not the script's targets, sets the final timing.

### Draft 1 (2026-08-29 01:10 to 01:45 UTC), synthetic voice

`video/` pipeline: `record.mjs` (Playwright drives the live console and logs a cue per narrated
moment), `narrate.py` (Google Cloud Text-to-Speech, en-US-Neural2-D, one wav per script line placed
at its cue), `assemble.py` (30 fps constant, Article 50 overlay, Grafana pages laid over the console
take, loudnorm, burned subtitles, `check.py --render`). Preparation done by the recorder itself:
rights mute on, one clean run, a 16-minute wait.

The take, 270.9 s, 28 cues, none timed out: Crest BLOCK content at 129.3 s (rights alone 62.7 s
after the three others), clean clip muted BLOCK control unavailable at 195.5 s, unmuted PASS at
240.9 s, dashboard, landing on the PASS card. `video/out/cues.json` and `narration.json` are kept.

`video/out/airlock-draft-1-synthetic-voice.mp4`, 176.9 s, 20.6 MB:

```
PASS  G41 definition  (1920x1080)      PASS  G45 niveau audio  (-16.4 LUFS, peak -4.1)
PASS  G42 cadence  (30.0 fps)          PASS  G46 silence  (plus long blanc 0.0s)
PASS  G43 duree  (177s)                PASS  G47 ouverture  (1 plage(s) de noir)
PASS  G44 audio present  (aac)         RESULTAT: PASS mecanique
```

To fix in draft 2: the assembler had to cut 86 s of waiting inside the runs to fit 180 s (the
compressed stretches get an on-screen label from draft 2 on); the first voice line ran 17.6 s
against an 8 s beat (script shortened); one subtitle cue per script line covered the timeline (per
sentence from draft 2); the first Grafana visit was captured before its panels drew (recorder waits
for the canvases now).

### Draft 2 (2026-08-29 02:00 to 02:55 UTC), synthetic voice

Changes: subtitles per sentence (28 cues over 13 lines, two rows at most); every cut inside a run
labelled on screen for the 2.5 s before it ("waiting for Video Intelligence, N s compressed") and
listed in `assembly.json`; the ASA page held 8 s; the Grafana overlays' black heads skipped.

The preparation had to be rebuilt: waiting 16 minutes after one muted run puts the three other
gates past the 900 s threshold as well, and the console then shows every card degraded. The
sequence is now one unmuted clean run, one muted run 13 minutes later, then a wait until the rights
gate is past 990 s (so the card reads "17 min ago" while the voice says seventeen minutes).

The take, 256.5 s, 28 cues, none timed out: Crest BLOCK content at 104.4 s, clean clip muted BLOCK
control unavailable at 166.6 s, unmuted PASS at 222.1 s. Compressions: 20 s, 21 s and 27 s of
rights-gate waiting; 4.8 s more came off the two holds to reach 178.5 s.

`video/out/airlock-draft-2-synthetic-voice.mp4`, 178.5 s, 19 MB:

```
PASS  G41 definition  (1920x1080)      PASS  G45 niveau audio  (-16.4 LUFS, peak -4.2)
PASS  G42 cadence  (30.0 fps)          PASS  G46 silence  (plus long blanc 0.0s)
PASS  G43 duree  (178s)                PASS  G47 ouverture  (0 plage(s) de noir)
PASS  G44 audio present  (aac)         RESULTAT: PASS mecanique
```

Open for the human pass: a 26.6 s stretch with no voice from 46 s to 73 s (the claim gate reading
the Crest film) which the script now fills with a line on the brand landing; whether 1.5 s of wait
kept before each labelled cut reads as a cut; the ASA scroll position; the landing hold.

## Continuity check (2026-08-29, 14:40 to 15:10 UTC, about 12 hours after draft 2)

A fresh session picked the build back up from a clean `git clone` of the public repo (no assumed
local state). It was briefed to continue M1; the repo already showed M1 through M4b DONE and M5 in
progress, so this pass is a regression and drift check before M5 resumes, not a repeat of M1. The
idea gate rerun is logged above under M1. Track decision stands: Grafana Labs, kill criterion not
triggered, no cause to switch to ClickHouse (Falsework).

### Live infra, unchanged from the M1 to M4b record

```
GET /api/health (airlock-console)   200  ok:true mock:false  4 gates read from Grafana, all "degraded"
                                          (last success 44000+ s ago: nothing has run in 12 hours,
                                          expected, not a defect; docs/DEMO-DAY.md step 1-2 already
                                          calls for a fresh calibration run before recording)
GET /api/stats (airlock-console)    200  {"checked_7d":23,"passed_7d":8,"blocked_7d":15,"incidents_7d":14,
                                          "gates_calibrated":4,"gates_total":4}
POST /mcp (airlock-mcp-grafana)     401  (bearer required, as built; service answers)
GET /public-dashboards/... (Grafana) 200
gcloud billing projects describe airlock-agentic-cinema --format="value(billingEnabled)"   True
gcloud run services list --region=us-central1        airlock-console, airlock-mcp, airlock-mcp-grafana, all present
reasoningEngines.list                                 1737023312967499776 (airlock), 1949818395360755712 (airlock-spike), both present
```

Nothing torn down, nothing expired, nothing renamed. The account is dylanmerigaud@gmail.com, as
the plan requires.

### Regression check on a clean checkout

```
uv sync                                    clean
uv run pytest -q                           44 passed, 2 skipped in 4.91s
                                            (the 2 skips are test_provenance.py needing
                                            scripts/fetch_assets.sh and make_synthetic_asset.sh,
                                            which a fresh clone has not run; not a code regression)
pnpm install && pnpm typecheck (console)   clean, no errors
pnpm lint (console)                        clean, no errors
pnpm build (console)                       Compiled successfully, all 6 routes generated
```

### The ASA scroll beat, checked against the live page, not re-guessed

Draft 2's write-up flagged "the ASA scroll position" as open for a human to watch. Read
`video/record.mjs:355-386` before touching anything: `scrollIntoViewIfNeeded` on the first
"assessment" text, then `window.scrollBy(0, 16)` every 90 ms for the full 8 s beat (about 86 steps,
1376 px). Ran that exact sequence against the real page with a throwaway Playwright script
(`video/asa_probe.mjs`, kept, no shipped pipeline changed, no GCP call, public page only):

```
assessment heading bbox: { x: 380, y: 2209.9, width: 760, height: 40.8 }
scrollY right after scrollIntoViewIfNeeded: 1690
document scrollHeight: 6586
steps: 86  total scrollBy px: 1376  final scrollY: 3066
visible text lines at end of beat:
  2. Upheld
  The CAP Code stated that medicinal or medical claims and indications could only ...
  We also understood that NutriPaw's Dental Powder was not licensed by the VMD for ...
  3. Upheld
  The ASA considered consumers would understand the claims "breaks down tartar cem ...
```

The beat starts on the assessment heading and ends inside the actual upheld reasoning, on topic
the whole way. Verdict: not a bug, no change made to `record.mjs`. The open item was a request for
a human eyeball, not a defect; this measurement answers it without needing to record a whole new
take to find out. If the ASA page's layout changes before the real recording, `asa_probe.mjs`
reruns in about 5 s with no GCP cost and no wait, so it stays in `video/` as a pre-flight check for
`docs/DEMO-DAY.md` step 1.

### What this pass did not do, and why

No new video draft was rendered. The other three open items from draft 2 (the 1.5 s compressed-cut
caption, the 26.6 s brand-landing gap, the landing hold) are paced/aesthetic calls the project's
own `video/README.md` already assigns to a human watching the footage, not to the render gates;
guessing at a fix and re-rendering without watching the result would spend real Video Intelligence
and Text-to-Speech calls against the 87.79 EUR hackathon credit for an unverified outcome, and the
whole take gets re-assembled again regardless once Dylan's real voice replaces the synthetic one.
The mechanical gates were rechecked instead, on the current text with no video yet:

```
check.py --type submission docs/DEVPOST.md   FAIL, G19 exigences du track (1 case non cochee)
                                               (the video checkbox; expected, everything else PASSes)
check.py --type video docs/VIDEO-SCRIPT.md    PASS mecanique (G37 WARN: render checklist unticked,
                                               normal before a shoot)
```

### What is actually left before 2026-09-03

- M5 (video): draft 2 exists (synthetic voice, PASS mecanique, 178.5 s). Next real step is Dylan
  watching draft 2 and deciding on the three open pacing items, then recording his own voice over
  the script (`video/README.md`), which is the one step this build session cannot do itself.
  `docs/DEMO-DAY.md` already has the runbook for the final take.
- M6 (repo and Devpost text): effectively done. `docs/DEVPOST.md` passes every gate except the
  video checkbox, which resolves the moment M5 does.
- M7 (practitioner quotes): two DMs are drafted and ready in `docs/PRACTITIONER-ASK.md`; sending
  them is explicitly Dylan's own action through his own doors, not this session's.

## M4, second pass: the console v2 (2026-08-29, after Dylan's review)

Dylan's review of the first console: a light theme, the media first and more prominent, less
crowding (views or collapsing), and the design vocabulary of the media tools reviewers already use.
Applied as: warm paper ground with one ember accent and a serif for the verdict word; the clip as
the stage (58 percent of the width, plays muted while the gates read it) with a scrubber carrying
one marker per timestamped finding, coloured by gate (Frame.io); the findings as a thread beside
the stage, a click on a marker or a time chip seeks the clip; the gates as a checklist with the
verdict summary on top, an icon, one status line and the Grafana calibration line per row, a
chevron onto the source of truth, the mute switch and the evidence (YouTube Studio's Checks); the
decision record (rules cited, C2PA, annotation, incident, human review) under the clip; Trace and
Queue as their own views. Every route, the SSE contract, mock mode and the fixtures unchanged.
Verified in mock mode: build, lint, typecheck clean; no horizontal overflow at 390 px; headings,
labels and names in order. Screenshots: `docs/img/console-v2-crest-block-2026-08-29.png`,
`docs/img/console-v2-clean-pass-2026-08-29.png`. Deploy and the Lighthouse rerun follow.

### Console v2 deployed (2026-08-29 19:00 UTC)

Revision `airlock-console-00004-5gr`, page in 1.4 s, the clip streams from Cloud Storage through
`/api/asset/crest` (206, video/mp4). Lighthouse on the hosted URL, desktop, navigation mode:
accessibility 100, best practices 100, SEO 100 (56 audits passed, none failed).

Dylan's second review (19:05 UTC): the page should fit the viewport and carry the maximum of
information at first sight, interactions switch views (unless the media is needed), dense but not
overloaded, no blinking effects, sober; and the palette should come from a known media tool rather
than be composed. The v3 pass applies it. The video draft 3 was stopped on his word.

## M4, third pass: the console v3 (2026-08-29)

Three changes, from that second review.

**One screen.** Above 1100 px the Review view is exactly the viewport: top bar, then the clip with
its scrubber and the asset strip on the left, the verdict and a `Checks | Findings | Record`
segmented control on the right, the five stats and the spec line as one thin bar at the bottom.
Each segment scrolls inside its own region, the page never does. Measured with headless chromium:
`document.documentElement.scrollHeight` equals `window.innerHeight` at 1440x900 in idle, on the
settled Crest run, on each of the three segments and on the clean PASS run, and at 1920x1080 in
idle and on the settled Crest run. Trace and Queue fit too. Below 1100 px it stacks and scrolls,
with no horizontal overflow at 390, 768 or 1099 px. Two defects were paid for on the way: a grid
row that grew past its container, and `sr-only` spans, which are absolutely positioned, escaping
the scroll box because `overflow` alone is not a containing block (`.fit-scroll` is now
`position: relative`).

**Sober.** Every looping animation is gone: the live lamp, the gate scan sweep, the row entrance
slide. `grep -rn "animate-\|@keyframes\|animation:" src` returns two lines, both the single
160 ms opacity fade. A running gate shows a static ring and its step in words. No gradient, no
glow, no shadow heavier than a hairline; the ruled-paper background is gone.

**Palette from YouTube Studio's light theme, literal.** Ground `#F9F9F9`, surfaces `#FFFFFF`,
hairlines `#E5E5E5` and `#CCCCCC`, text `#0F0F0F` and `#606060`, accent `#065FD4`, BLOCK
`#CC0000`, PASS `#1E8E3E`, degraded `#B06000`, muted chip on `#F1F1F1`. Roboto 400/500/700 and
Roboto Mono through `next/font/google`; Sora, Newsreader and IBM Plex Mono are gone. Gate hues
desaturated to sit on white: rights `#3B6FA0`, claim `#9A3D7A`, brand `#2E7D6B`, provenance
`#7B4FA8`, all above 4.9:1 against `#FFFFFF`.

One deliberate departure, measured: `#1E8E3E` is 4.20:1 on white, which clears the 3:1 a
non-text mark needs and not the 4.5:1 small text needs. Green therefore carries the check icons,
the rules and the 28 px verdict word (large text, 3:1); every small PASS label is set in ink
beside a green mark. Amber `#B06000` is 4.65:1 on white and 4.42:1 on the ground, so it is only
ever set on a white surface. axe-core 4.10.2, wcag2a + wcag2aa + wcag21a + wcag21aa +
best-practice: zero violations on idle, on the settled run, on all three segments, on Trace and
on Queue. The skip link now targets `<main id="main-content">` instead of the stage, which only
exists in the Review view.

Every route, the SSE contract, mock mode, the fixtures, the three presets and the upload are
untouched. `pnpm build`, `pnpm lint` and `pnpm typecheck` clean.

### Console v3 deployed (2026-08-29 19:43 UTC)

Revision `airlock-console-00005-rvs`, page in 1.5 s. One screen at 1440x900 and 1920x1080
(document height equals the viewport in every state, measured by the build agent in headless
chromium and in Arc), YouTube Studio's light palette and Roboto, no looping animation, the right
column segmented into Checks, Findings and Record. Lighthouse on the hosted URL, desktop,
navigation mode: accessibility 100, best practices 100, SEO 100 (56 audits passed, none failed).
axe-core in the build: zero violations on every view. Screenshots:
`docs/img/console-v3-crest-block-2026-08-29.png`, `docs/img/console-v3-clean-pass-2026-08-29.png`.
The video (M5) is on hold at Dylan's word until the console is where he wants it; the recorder
will be adapted to this DOM before draft 3.

## Cost and the cap (2026-08-29)

Read from the billing console on 2026-08-29 20:10 UTC (screenshots in the session scratchpad):
credit "Agentic Cinema Hackathon" 87.79 EUR, 85.50 EUR remaining (97 percent), valid to
2026-10-19; month-to-date gross 2.40 EUR (Vertex AI 2.27, Cloud Run 0.14; Video Intelligence
inside its monthly free quota so far), net 0.00. A card is on file and the account is a paid one,
so the guard is not the credit but the cap below.

Guard (`infra/gcp/billing_cap.sh`): a budget "airlock hackathon credit" of 87 EUR on the GROSS cost
of the project (credits excluded, so it measures how much of the credit is consumed; rounded down
from 87.79 so it fires before the last 79 cents), alerts to the billing admins at 50, 75, 90 and
100 percent, and every update published to the Pub/Sub topic `billing-cap`; a Cloud Function
(`infra/gcp/billing-cap/main.py`, service account `billing-cap@`, billing admin on the account)
detaches the project from the billing account when the cost reaches the budget. Dry-tested with a
published message at 1.25 EUR: the function logged the amounts and touched nothing.

Cost is also a product metric from here on: the gates push their token counts, video seconds and
an estimated cost per run, so the console and the dashboard can show what one check costs.

### Draft 3 (2026-08-29 21:20 to 23:03 UTC), on the console v3, synthetic voice

Recorder rewritten for the v3 DOM (preset cards by name, gate landings read off the Checks rows,
the verdict off the summary line, the mute switch inside the rights row, the Grafana href from
Record); narration mapped to cues by name from the script's `(cue xxx)` marks; one second of wait
kept before each labelled cut; a `seek_claim` beat (the clip seeks to the claim's timestamp on
camera). One take was thrown away when the rights gate was still checking at the 200 s bound (a
slow Video Intelligence call), the preparation redone, the second take clean.

The take, 253.6 s, 29 cues, none timed out: Crest BLOCK content at 123.5 s (incident 17), clean
clip muted BLOCK control unavailable at 172.0 s (incident 18), unmuted PASS at 222.3 s. The clip
played on the stage through the three runs. Compressions: 45 s, 4 s and 22 s of rights-gate waiting,
each labelled on screen; no hold trimmed.

`video/out/airlock-draft-3-synthetic-voice.mp4`, 176.9 s, 40.5 MB:

```
PASS  G41 definition  (1920x1080)      PASS  G45 niveau audio  (-16.4 LUFS, peak -4.0)
PASS  G42 cadence  (30.0 fps)          PASS  G46 silence  (plus long blanc 0.0s)
PASS  G43 duree  (177s)                PASS  G47 ouverture  (2 plage(s) de noir)
PASS  G44 audio present  (aac)         RESULTAT: PASS mecanique
```

Open for the human pass: the first Grafana insert shows about 8 s of the dashboard loading (the
recorder knows when the panels drew; the overlay should start there); the native video controls
are on screen the whole film (a console decision: custom controls or hidden chrome during a run);
the claim-seek words fall after the picture; a 14 s stretch with no voice in the third run.

### Cost metric deployed (2026-08-29 23:08 UTC)

Pipeline redeployed on `reasoningEngines/1737023312967499776` with `airlock/cost.py`: every gate
run carries `usage` (tokens in and out, video minutes, features, cost at list price) and pushes
`airlock_gate_cost_usd`; the verdict sums the run and pushes `airlock_verdict_cost_usd`. Console
revision `airlock-console-00006-6q5`: "Cost per check" in the footer (7-day list-price average,
`null` until a verdict has run through the new agent, never a placeholder), the run's cost line in
the Record segment, the usage line in each expanded gate row. Dashboard version 4: "Cost per check"
and "Cost per gate run" panels. First measured gate cost: the claim gate on the clean clip, 2,223
tokens in and 131 out on gemini-2.5-pro, 0.0041 USD; a 30 s clip through the four Video
Intelligence features, 1 started minute, 0.50 USD at list price (free quota not netted).

### Console revision 7 (2026-08-29 23:32 UTC)

`airlock-console-00007-lpk`: the stage carries the console's own controls (play or pause, mute,
the marker scrubber as a keyboard-operable slider, Space and arrow keys on the stage), no native
video chrome, so the demo video shows no player bar. Known and left: on a page whose clip cannot
stream (a console without Cloud Storage credentials), the "cannot play" state is set by an event
that a hydration race sometimes misses, so the buttons can render enabled; the hosted console
streams its clips, so the state does not arise there.

## M6a: gate evaluation on 16 assets

Status: DONE 2026-08-29 (23:03 to 23:37 UTC, 2042 s wall for all 16 assets, sequential).

Ten more Prelinger commercials selected through the archive.org advanced search, one per category
(cereal, cars, soap, cameras, coffee, beer, toys, toothpaste other than Crest, tissues, appliances),
excerpts cut and uploaded, none of them CrestToothpa: `assets/real/eval/SOURCE.md`. The eval runner,
`scripts/eval_gates.py`, runs the four gates on these ten plus the six synthetic assets already in
the repo (`nimbus-test-clip`, `nimbus-clean-clip`, the three calibration defects, `veo-raw`), one
asset at a time so Video Intelligence never has two jobs running together, with
`AIRLOCK_RUNTIME=eval` so the telemetry is labelled apart from the console and calibration runs.
This run waited on the demo video's draft 3 to finish rendering and checking first (a file drop at
23:03:08 UTC from the other agent recording it), then started at 23:03:27, 19 seconds later, so the
two never shared Video Intelligence quota.

Commands:

```
scripts/with_env.sh uv run python scripts/eval_gates.py --list   # the 16 asset ids and their sources
nohup scripts/with_env.sh uv run python scripts/eval_gates.py > eval/logs/run-20260829T230327Z.log 2>&1 &
```

Full output: `eval/results.json` (every GateResult, per asset per gate), `eval/EVAL.md` (the table
below, precision and recall, latency, what claim and brand found on the ten real spots unscored).

### Summary table

| asset | kind | rights | claim | brand | provenance | wall |
|---|---|---|---|---|---|---|
| Cheerios1960-0-30 | real | BLOCK 83.1 s | BLOCK 23.2 s | BLOCK 21.8 s | BLOCK 34 ms | 137.7 s |
| chevrolet-31-61 | real | BLOCK 142.7 s | BLOCK 39.9 s | BLOCK 31.1 s | BLOCK 1 ms | 223.7 s |
| ivory_soap-25-55 | real | BLOCK 28.6 s | BLOCK 21.6 s | BLOCK 19.6 s | BLOCK 2 ms | 78.6 s |
| kodak_instamatic-31-60 | real | BLOCK 47.1 s | BLOCK 18.2 s | BLOCK 18.5 s | BLOCK 2 ms | 92.9 s |
| folgers-26-56 | real | BLOCK 85.4 s | BLOCK 20.1 s | BLOCK 18.9 s | BLOCK 1 ms | 133.4 s |
| labatts_beer-0-20 | real | BLOCK 48.4 s | BLOCK 33.6 s | BLOCK 16.9 s | BLOCK 2 ms | 107.8 s |
| gilbert_slot_racers-0-30 | real | BLOCK 457.9 s | BLOCK 17.4 s | BLOCK 20.0 s | BLOCK 2 ms | 504.3 s |
| MacleansToot-0-29 | real | BLOCK 39.9 s | BLOCK 22.4 s | BLOCK 17.2 s | BLOCK 2 ms | 88.7 s |
| ScottiesTiss-0-30 | real | BLOCK 60.0 s | BLOCK 23.7 s | BLOCK 15.2 s | BLOCK 1 ms | 109.2 s |
| GE_blender-0-30 | real | BLOCK 51.8 s | BLOCK 19.5 s | BLOCK 15.7 s | BLOCK 2 ms | 99.5 s |
| nimbus-test-clip | synthetic | PASS 32.4 s | BLOCK 16.7 s | PASS 12.6 s | PASS 23 ms | 70.6 s |
| nimbus-clean-clip | synthetic | PASS 34.0 s | PASS 12.1 s | PASS 8.6 s | PASS 7 ms | 63.6 s |
| nimbus-defect-brand-red | synthetic | PASS 33.8 s | PASS 13.7 s | BLOCK 22.3 s | BLOCK 2 ms | 78.7 s |
| nimbus-defect-provenance-stripped | synthetic | PASS 37.3 s | BLOCK 16.1 s | PASS 10.8 s | BLOCK 1 ms | 73.0 s |
| nimbus-defect-provenance-broken | synthetic | PASS 46.1 s | BLOCK 10.0 s | PASS 13.9 s | BLOCK 7 ms | 79.2 s |
| veo-raw | synthetic | PASS 66.3 s | PASS 11.2 s | BLOCK 14.4 s | BLOCK 12 ms | 100.8 s |

### Precision and recall, where a ground truth exists

BLOCK is the positive class. All four gates scored perfectly against the ground truth stated in
the task and in `assets/real/eval/SOURCE.md`:

```
rights      n=13  tp=10 fp=0 tn=3 fn=0   precision 100%  recall 100%
claim       n=3   tp=1  fp=0 tn=2 fn=0   precision 100%  recall 100%
brand       n=4   tp=2  fp=0 tn=2 fn=0   precision 100%  recall 100%
provenance  n=15  tp=13 fp=0 tn=2 fn=0   precision 100%  recall 100%
```

rights and provenance are scored over every real spot (BLOCK expected) plus whichever synthetic
assets carry a stated expectation for that gate; claim and brand are scored only where the task
gave one (the real spots have no charter or substantiation file, so they are reported, not scored,
in the "what claim and brand found" section of `eval/EVAL.md`).

### Latency per gate, over all 16 assets

```
rights       median 47.7 s   max 457.9 s (gilbert_slot_racers-0-30)
claim        median 18.9 s   max 39.9 s (chevrolet-31-61)
brand        median 17.0 s   max 31.1 s (chevrolet-31-61)
provenance   median 2 ms     max 34 ms (Cheerios1960-0-30)
```

Cost, from the usage the gates now report (`airlock/cost.py`, deployed to the cloud pipeline the
same evening): $8.2262 at list price for the whole run, 16 Video Intelligence minutes (one started
minute per asset, four features), 32 Gemini calls (one claim call on gemini-2.5-pro and one brand
call on gemini-2.5-flash per asset). Median $0.5182 and maximum $0.5213 per asset for the ten real
spots (four Video Intelligence features plus two Gemini calls each); the six synthetic assets cost
about $0.505 to $0.506 each, slightly less, on shorter clips.

### Surprises

- **The rights gate names the wrong brand on six of the ten real spots, and still blocks for the
  right reason.** Video Intelligence's logo recognition confidently (0.85 to 0.92) tags mid-century
  logos it was never trained on as unrelated modern brands: the 1963 Chevrolet spot as "DeLorean
  Motor Company", the Kodak Instamatic spot as "Ichiran" (a ramen chain), the Labatt's beer spot as
  "Peugeot", the Gilbert slot-car spot as "Vauxhall Motors", the Scotties tissue spot as "Lucid
  Motors", the GE blender spot as "Target Corporation". Only Ivory and Folgers were named correctly,
  and Cheerios came back as "Honey Nut Cheerios". None of these six wrong names sit in
  `rights-registry.yaml` either, so the gate's policy (`unknown_brand: BLOCK`) fires anyway and the
  verdict is right by coincidence, not by having read the label correctly. A human clearing rights
  on the evidence alone would be looking for a licence from the wrong company.
- **MacleansToot never triggered a brand finding at all.** Logo recognition did not name Macleans,
  and on-screen text detection only checks for registry brand names, so a brand the registry has
  never heard of cannot be caught that way either. The gate still blocked, on `registry:faces:no_release`
  (10 face tracks, the two skiers), a real finding but not the one this asset was chosen to test.
- **veo-raw is not unsigned.** The task's own ground truth called it "unsigned"; the provenance gate
  found a valid C2PA manifest issued by Google LLC (Vertex AI stamps Veo's raw output with its own
  manifest) and blocked on `airlock:provenance:signer-trusted`, not `manifest-required`, because
  Google is not on Airlock's studio trust list. The BLOCK is correct, the mechanism assumed for it
  was not.
- **One Video Intelligence call took 458 seconds** (gilbert_slot_racers-0-30, rights gate) against a
  median of 47.7 s and every other real spot under 143 s, even though this run never had two jobs
  in flight at once by its own design. Consistent with the variance already logged in M2 ("598 s
  when three jobs ran at once"), so quota contention from elsewhere on the project is the leading
  explanation, but this run has no direct evidence of what else was running at 23:22 to 23:30 UTC.
- **A reported reason can hide a second catch.** `nimbus-defect-brand-red`'s brand gate reports
  "exclusion violated: no discount or price" first (the code surfaces only the first reason string),
  but its `rule_ids` carry both `charter:exclusions` and `charter:palette`: the forbidden red banner
  was caught too, just not the one named in the printed line.
- **Every real spot's claim gate found a regulated claim, and every one is a different kind**: a
  superlative ("an out-of-this-world breakfast", Cheerios), a testimonial ("I'm going to see the
  1963 Chevrolets", Chevrolet), a health claim ("Ivory's natural soap"), an efficacy claim ("Take
  four flash pictures without changing bulbs", Kodak), a comparative ("You just need the coffee
  with better flavor", Folgers). Sixty-year-old copywriting maps onto 16 CFR 255 as cleanly as the
  demo asset does.

### Draft 4 (2026-08-29 23:38 to 2026-08-30 00:15 UTC), on the console v3 with its own stage controls, synthetic voice

Three things changed before the take. The Grafana inserts now start when the panels have drawn:
the recorder logs `grafana_ready` and `dashboard_ready` at that instant and writes it into the
overlay entry as `ready_at`, and the assembler starts each insert there instead of at the page
opening, with the blackdetect head kept as the fallback. The claim seek keeps its cue and gains
`seek_done`, so the compressed rights wait starts where the beat actually ends instead of four
seconds after it. The script's claim line now opens with "Click the time and the clip goes there"
and the third run carries two lines (`provenance_done_3`, `claim_done_3`), both placed by name.
Selectors re-read on the live page first: the stage has no native video controls any more (its own
play, pause and mute buttons and a marker slider), and nothing the recorder reads moved.

The take, 325.0 s, 32 cues, 0 notes, none timed out: Crest BLOCK content at 120.2 s (incident 19),
clean clip muted BLOCK control unavailable at 245.8 s (incident 20), unmuted PASS at 295.0 s. The
rights gate waited 35 s, 71 s and 22 s over the three runs and the first Grafana insert took 19.1 s
to draw, which left the render at 185.0 s measured with only the rights waits compressible, over
the 180 s limit on a take that was otherwise clean. So the assembler now also compresses the wait
for a Grafana insert to draw, under its own caption ("waiting for Grafana to draw, N s compressed")
and with the same one second kept on screen: what it removes is still nothing but waiting, and it
still says so on the picture. Nothing under a second is ever cut now either, so no caption can read
"0 s compressed". Compressions: 35 s of Video Intelligence, 18 s of Grafana drawing, then 71 s and
22 s of Video Intelligence, each labelled; no hold trimmed.

`video/out/airlock-draft-4-synthetic-voice.mp4`, 177.2 s, 39.0 MB:

```
PASS  G41 definition  (1920x1080)      PASS  G45 niveau audio  (-16.4 LUFS, peak -4.0)
PASS  G42 cadence  (30.0 fps)          PASS  G46 silence  (plus long blanc 0.0s)
PASS  G43 duree  (177s)                PASS  G47 ouverture  (1 plage(s) de noir)
PASS  G44 audio present  (aac)         RESULTAT: PASS mecanique
```

Open for the human pass: the footer's "Cost per check" and the dashboard's cost panel both read
$0 on camera (`/api/stats` returns `cost_per_check_usd_7d: 0`), which reads as free rather than as
a 7-day average that has only just started being written; the verdict line is spoken over the first
Grafana insert rather than over the verdict card it describes, because the card fills four seconds
before the insert opens; and the Grafana caption puts a fourth editing note on the picture.

### Cost verified live, the length rule, the pace direction (2026-08-30 00:22 to 00:40 UTC)

Agent redeployed with `pricing.yaml` in the package (the draft 4 take had shown "$0": the file was
not shipped, so no gate could price itself). Console revision `airlock-console-00008`: a run whose
cost is not measured says so. Verified through the hosted console on the clean clip (annotation
44): rights 1 min x 4 features 0.50 USD, claim 2,223 in and 142 out on gemini-2.5-pro 0.0042 USD,
brand 2,504 in and 161 out on gemini-2.5-flash 0.0012 USD, provenance 0; the run 0.505 USD.

The video length rule, read on the Devpost rules page on 2026-08-30 (verbatim): "It should not be
longer than 3 minutes. If it is longer than 3 minutes, only the first 3 minutes will be
evaluated." Dylan's direction the same evening: the winners' length but "ultra dynamic". Script v5
cuts for pace: the ASA beat gone, the stake overlay 5 s, the first run at 0:12, the verdict card
held for its line then a 5 s dashboard insert, a punch-in on every landing, the voice at 1.1x,
half a second of wait kept before each labelled cut, target 150 to 170 s. Draft 5 in production.

### Draft 5 (2026-08-30 01:07 to 01:31 UTC), script v5, cut for pace, synthetic voice

Script v5 in the pipeline. The recorder drops the ASA page (`--skip-asa` is the default now, `--asa`
brings it back), holds the stake 5.5 s under a 5 s Article 50 overlay, and holds the verdict card
for as long as the line spoken over it: it reads that length out of `narration.json`, which is why
the narration is now synthesised once before the take and once after it. The Record segment stays
on camera a second and a half and the recorder reads the run's cost line out of it into a cue. Each
Grafana insert holds still for two seconds and then glides down the panels, and says from when to
when it was actually moving. The narration is at speaking rate 1.1 with the silence trimmed off
both ends of every wav, which is 6.8 s over nineteen lines and, more to the point, 6.8 s of lines
not being pushed off the picture they describe.

The assembler stopped aiming at a length. Every wait comes off whole, down to the half second the
caption is spoken over, and two more kinds of waiting are now cut under the same promise: the
seconds between two gates landing once the line about the first has been said ("waiting for the
claim gate, N s compressed") and the seconds the verdict agent spends asking Grafana before the
card fills ("waiting for the verdict agent, N s compressed"), both only when they take out four
seconds or more, because a caption costs the picture more than three seconds of waiting does. Two
captions that would have been drawn on top of each other now queue. Under 150 s whole waits go back
on the picture, shortest first and never one over six seconds, which is what happened here: full
compression left the picture at 133.1 s against a narration ending at 139.0 s, so seven seconds of
the render would have been a frozen last frame, and giving four short waits back put the picture
ahead of the voice again.

Every landing gets a punch-in, 1.15x over 1.2 s eased in and out, on the Checks column for a gate,
the verdict summary for a verdict, the stage for the claim seek. The centres are measured on the
live console by `video/measure_layout.mjs` (verdict card 1484,59 420x76; the six check rows
1485,182 418x405; the stage 16,59 1456x916). At 1.15x the frame can only travel 125 px across and
70 px down before the crop would leave the picture, so the right column punches all clamp to
1085,470 and the stage punch to 835,517; `assembly.json` carries both the centre asked for and the
one reached. Thirteen played, three dropped: `claim_done` because the seek lands on the stage in
the same instant, `rights_done_2` and `rights_done_3` because they land inside the claim punch on
the same centre.

The take, 283.6 s, 32 cues, no timeout, one note (no ASA beat): Crest BLOCK content at 85.1 s
(incident 21), clean clip muted BLOCK control unavailable at 204.5 s (incident 22), unmuted PASS at
256.6 s. The rights gate waited 21 s, 56 s and 26 s, the first Grafana insert took 17.9 s to draw.
Compressions: 21 s of Video Intelligence, 17 s of Grafana drawing, 56 s of Video Intelligence, 7 s
of the verdict agent, 26 s of Video Intelligence, 127.5 s in all, each labelled; no hold trimmed.
The cost line was on camera in the Record segment and read $0.52 at list price (rights $0.50, claim
$0.02, brand $0.004, provenance $0), 17,629 tokens in, 1,282 out, 1 min of video; the footer read
$0.03 per check at the open and $0.06 at the landing, and the dashboard panel $0.0453.

`video/out/airlock-draft-5-synthetic-voice.mp4`, 151.3 s, 41.7 MB:

```
PASS  G41 definition  (1920x1080)      PASS  G45 niveau audio  (-16.4 LUFS, peak -4.1)
PASS  G42 cadence  (30.0 fps)          PASS  G46 silence  (plus long blanc 0.0s)
PASS  G43 duree  (151s)                PASS  G47 ouverture  (0 plage(s) de noir)
PASS  G44 audio present  (aac)         RESULTAT: PASS mecanique
```

The pace measurement, which is the point of the draft: the longest stretch of the render with
neither a change of picture nor a line playing is 6.40 s, at 43.4 s, between the brand line ending
and the claim gate landing, with the clip playing on the stage and the claim row reading "Checking"
under it. That stretch is one of the four waits given back to keep the render over 150 s; cut, it
would have been 4.65 s, and the worst would then have been the tail of the 5 s Grafana insert,
whose line lasts 1.6 s. The 2 s rule is not reachable while a 5 s insert carries a 1.6 s line, and
the two numbers are the trade: 151.3 s with a 6.40 s stretch, or 140.2 s with a 4.65 s one and
seven seconds of frozen picture at the end. Voice covers 117.4 s of the 151.3 s, and the render
carries 38 changes of picture outside it.

Open for the human pass: whether the punch-ins read as a push towards the column that changed or
as a wobble, since a 1.15x move on a 1920x1080 frame is a small one; whether five editing captions
in 151 s read as honesty or as clutter; and whether the 6.40 s stretch at 43.4 s is felt as slow.

## Audit after two idle days (2026-09-02, 23:50 to 00:20 UTC)

Dylan's ask on 2026-09-02: audit, reorient, list the best things to do now; the final video is not
the priority. Read before writing: repo equals origin (fc9e777, clean tree), 53 tests pass, no
dash character in any tracked file, no vendor mention outside the MCP client example, no secret
pattern, no trailer in any commit. The three Cloud Run services answer (console 200 in 4.3 s cold,
the two MCP servers 401 without a bearer, as designed).

What the cold read found, in the order it matters:

1. **The calibration window is 7 days and calibration was manual.** Rule R2 needs a catch in
   `[7d]`; the last ledger run was 2026-08-30. From 2026-09-06 every run would have ended in BLOCK
   "uncalibrated control" and the 7 day tiles would have read zero, with judging starting on
   2026-09-09. Remedy: the scheduled daily proof, section M8 below.
2. **The Grafana Cloud free stack pauses after idle days.** At 23:54 UTC `/api/health` and
   `/api/stats` answered `Grafana answered 503: {"code":"Loading","message":"Your instance is
   loading, and will be ready shortly."}`; the stack answered 200 about two minutes later. The
   console showed six red "unavailable" tiles with that JSON in a tooltip and did not retry.
   Remedy: the daily proof keeps traffic on the stack; the console retries (section below).
3. **The public dashboard opens on the last 6 hours**, which is empty unless someone just ran a
   check. Remedy: default range 7 days.
4. **The judge's whole wait is Video Intelligence.** The clean 8 s clip run from Agent Engine at
   23:58 UTC: provenance 0.7 s, brand 9.5 s, claim 15.3 s, rights 173.5 s; verdict PASS
   (content), annotation 50, 189.1 s in all. The eval median for rights was 47.7 s. Measured
   next: one operation with four features against four parallel one-feature operations.
5. **The Devpost video box is the only unticked requirement**: `check.py --type submission
   docs/DEVPOST.md` fails on G19 alone. Remedy: draft 5 uploaded unlisted as the placeholder, the
   final replaces the link.

Spend, read from the budget notifications the cap function logs every 25 minutes: August closed
at 3.49 EUR gross (the whole build: spike, eval, five drafts), September at 0 so far (billing
lags a day). Agent Engine bills nothing while idle. The credit (87.79 EUR, valid to 2026-10-19)
is essentially untouched.

Housekeeping: a `curl -X POST` on the reasoningEngines collection, meant as a list, created an
empty engine (`6039069264827121664`, 23:55:07 UTC); deleted at 23:57 UTC. The M1 spike engine
`airlock-spike` (`1949818395360755712`) deleted with its sessions at 00:12 UTC (`?force=true`,
the API refuses otherwise); the M1 section above stays as the record of what it proved.

A browser agent played a cold judge on the hosted URL (00:00 to 00:10 UTC, lane isolated,
screenshots kept in the session scratchpad): Crest BLOCK content in 78 s (annotation 51,
incident 23), clean clip PASS in 38 s (annotation 52); scores 4, 3, 4, 4 on the four criteria,
Design lowest. Its findings drive the console pass below: red "unavailable" and amber "degraded"
before any click, the Nimbus brand book never introduced, the verdict row's "0 of 4 gates
probed" beside the header's "3 of 4 reported", 40 s of silent rights gate, the run lost after the
Grafana detour, "78175 ms", the "Findings 4" badge on a clean PASS.

## M8: the daily proof (2026-09-02)

Status: DONE 2026-09-02 (00:30 UTC).

Why. The verdict trusts a gate only if Grafana has seen it catch an injected defect in the last 7
days (R2, `CALIBRATION_WINDOW = "7d"`), and calibration was a command someone ran by hand, last on
2026-08-30. Judges test the hosted console from 2026-09-09: by then every gate would read
"uncalibrated", every run would end in BLOCK "uncalibrated control", and the 7-day stats would read
zero. The Grafana Cloud free stack also pauses after idle days (observed 2026-09-01 23:54 UTC,
"Your instance is loading", about two minutes to wake). So the control now proves itself on a
schedule, which is a product feature as much as a fix: a gate that stops catching its defect loses
its right to PASS on its own, on the dashboard, without anyone reading a log.

Shape. `airlock/daily_proof.py` (`python -m airlock.daily_proof`) downloads the calibration inputs
from GCS when missing, runs the full calibration through `airlock.calibrate`'s own functions,
runs the clean clip through the deployed pipeline over `:streamQuery`, prints one JSON summary
line, pushes `airlock_daily_proof_total{outcome="pass"|"fail"}` and exits 0 only when every defect
was CAUGHT and the verdict is PASS. The streaming client moved from `scripts/query_agent_engine.py`
into `airlock/engine_client.py`; the script imports it, so the CLI, the proof and the console read
the same endpoint. `Dockerfile.proof` and `infra/gcp/daily_proof.sh` build the image on Cloud
Build, deploy the Cloud Run job `airlock-daily-proof` (us-central1, 1 CPU, 2 GiB, 1800 s, one
retry, the default compute service account, the same env and secrets as airlock-mcp plus
`AGENT_ENGINE_RESOURCE`) and a Cloud Scheduler job of the same name at `0 */12 * * *` UTC that
calls the Cloud Run Admin API's `:run` endpoint as `daily-proof-scheduler@`, a service account
holding `roles/run.invoker` on this job and nothing else. Eleven unit tests cover the summary and
exit logic, the input download and the SSE parsing, with no cloud call (`tests/test_daily_proof.py`).

One deviation from the brief: the scheduler authenticates with an OAuth access token, not an
OIDC identity token. The target is a Google API (`run.googleapis.com`), and Google APIs take OAuth
access tokens; an OIDC token is what a Cloud Run service or a Cloud Function behind IAM would
take. This is the documented pattern for running a Cloud Run job from Cloud Scheduler.

### Build and deploy (`bash infra/gcp/daily_proof.sh`, 00:15 to 00:18 UTC, run twice to check it is idempotent)

```
apis: run, cloudscheduler, cloudbuild, artifactregistry enabled
Created [https://cloudbuild.googleapis.com/v1/projects/airlock-agentic-cinema/locations/global/builds/794fe920-afa7-4896-b5e9-ddf777063841].
794fe920-afa7-4896-b5e9-ddf777063841  2026-09-02T00:15:45+00:00  53S  ...  us-central1-docker.pkg.dev/airlock-agentic-cinema/airlock/airlock-daily-proof  SUCCESS
Creating job...
Job [airlock-daily-proof] has successfully been deployed.
Created service account [daily-proof-scheduler].
daily-proof-scheduler@airlock-agentic-cinema.iam.gserviceaccount.com holds roles/run.invoker on job airlock-daily-proof
scheduler job airlock-daily-proof created: 0 */12 * * * UTC
projects/airlock-agentic-cinema/locations/us-central1/jobs/airlock-daily-proof  0 */12 * * *  Etc/UTC  https://run.googleapis.com/v2/projects/airlock-agentic-cinema/locations/us-central1/jobs/airlock-daily-proof:run  daily-proof-scheduler@airlock-agentic-cinema.iam.gserviceaccount.com  ENABLED
```

The second run (build `314b011b`, 38 s, 00:17:38 UTC) reported "Job [airlock-daily-proof] has
successfully been deployed", "Updated IAM policy for job" and "scheduler job airlock-daily-proof
updated": nothing created twice. The job as deployed: `taskCount 1`, `timeoutSeconds 1800`,
`maxRetries 1`, `cpu 1`, `memory 2Gi`, `serviceAccountName 771466810465-compute@developer.gserviceaccount.com`,
env `AIRLOCK_PROJECT`, `AIRLOCK_ASSETS_BUCKET`, `AIRLOCK_RUNTIME=daily-proof`, `AGENT_ENGINE_RESOURCE`,
the four Grafana URL and user variables, and the two tokens from Secret Manager. The job's IAM
policy has one binding: `daily-proof-scheduler@` as `roles/run.invoker`.

### Execution 1, by hand (`gcloud run jobs execute airlock-daily-proof --region us-central1 --wait`, 00:18:54 to 00:23:19 UTC)

```
Running execution...done
Done.
Execution [airlock-daily-proof-gqt9f] has successfully completed.
```

The job's log (`gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="airlock-daily-proof" AND labels."run.googleapis.com/execution_name"="airlock-daily-proof-gqt9f"'`):

```
00:21:08  inputs: 6 downloaded (assets/real/CrestToothpa-18-48.mp4, assets/synthetic/calibration/nimbus-clean-clip.mp4, assets/synthetic/calibration/nimbus-defect-brand-red.mp4, assets/synthetic/calibration/nimbus-defect-provenance-broken.mp4, assets/synthetic/calibration/nimbus-defect-provenance-stripped.mp4, assets/synthetic/nimbus-test-clip.mp4)
00:22:15  rights      CAUGHT   65869 ms  real trademark not cleared, faces without release  ->  BLOCK ['registry:brands:not_cleared', 'registry:faces:no_release']
00:22:15  claim       CAUGHT   15151 ms  expert endorsement with no substantiation  ->  BLOCK ['16 CFR 255.3', 'ASA A26-1337640 (CAP 3.7)']
00:22:15  brand       CAUGHT   24399 ms  forbidden red banner and urgency copy  ->  BLOCK ['charter:exclusions', 'charter:palette']
00:22:15  provenance  CAUGHT     476 ms  manifest stripped  ->  BLOCK ['airlock:provenance:manifest-required']
00:22:15  provenance  CAUGHT     532 ms  signed copy with one byte flipped  ->  BLOCK ['airlock:provenance:signature-valid']
00:22:20  [   1.0s] rights_gate      running  rights
00:22:20  [   1.1s] claim_gate       running  claim
00:22:20  [   1.3s] brand_gate       running  brand
00:22:20  [   1.5s] provenance_gate  running  provenance
00:22:22  [   3.2s] provenance_gate  PASS      184 ms  C2PA manifest verified and trusted; signed by Airlock (hackathon test); created by airlock-synthetic-asset
00:22:32  [  13.1s] brand_gate       PASS    10102 ms  Nimbus wordmark seen, palette, tone and exclusions respected
00:22:34  [  15.0s] claim_gate       PASS    12286 ms  no regulated claim without substantiation (1 claim(s) read, 1 advisory)
00:23:06  [  47.5s] rights_gate      PASS    45031 ms  cleared brand(s): Nimbus; no unreleased face, no explicit content
00:23:09  [  50.0s] verdict          grafana  rights      healthy, last success 3 s ago; caught 4 injected defect(s) in 7d  {'error_rate_15m': 0.0, 'seconds_since_success': 3.49, 'calibration_catches_7d': 4.0, 'last_calibration_caught': 1.0}
00:23:10  [  51.1s] verdict          grafana  claim       healthy, last success 37 s ago; caught 5 injected defect(s) in 7d  {'error_rate_15m': 0.0, 'seconds_since_success': 37.6, 'calibration_catches_7d': 5.0, 'last_calibration_caught': 1.0}
00:23:11  [  52.2s] verdict          grafana  brand       healthy, last success 40 s ago; caught 4 injected defect(s) in 7d  {'error_rate_15m': 0.0, 'seconds_since_success': 40.7, 'calibration_catches_7d': 4.0, 'last_calibration_caught': 1.0}
00:23:12  [  53.4s] verdict          grafana  provenance  healthy, last success 51 s ago; caught 8 injected defect(s) in 7d  {'error_rate_15m': 0.0, 'seconds_since_success': 51.8, 'calibration_catches_7d': 8.0, 'last_calibration_caught': 1.0}
00:23:13  [  54.4s] verdict          VERDICT PASS (content) needs_human=False annotation=53 6065 ms
                                     all 4 gates PASS, healthy and calibrated
00:23:13  [  54.7s] escalation       escalation: no human needed: verdict PASS on content
00:23:15  {"annotation_id": 53, "calibration_cost_usd": 0.506388, "clean_clip_cost_usd": 0.505163, "cost_usd": 1.011551, "elapsed_s": {"calibration": 70.9, "clean_clip": 54.7, "inputs": 2.1}, "gates": {"brand": "CAUGHT", "claim": "CAUGHT", "provenance": "CAUGHT", "rights": "CAUGHT"}, "motive": "content", "outcome": "pass", "reasons": [], "verdict": "PASS", "calibration": [{"gate": "rights", "caught": true, "cost_usd": 0.5, "elapsed_ms": 65869}, {"gate": "claim", "caught": true, "cost_usd": 0.004739, "elapsed_ms": 15151}, {"gate": "brand", "caught": true, "cost_usd": 0.001649, "elapsed_ms": 24399}, {"gate": "provenance", "caught": true, "cost_usd": 0, "elapsed_ms": 476}, {"gate": "provenance", "caught": true, "cost_usd": 0, "elapsed_ms": 532}]}
00:23:15  Container called exit(0).
```

The summary line lands in Cloud Logging as a `jsonPayload` (the runtime parses JSON lines), so it
is read with `AND jsonPayload.outcome:*` rather than `textPayload`. The calibration rows now carry
`cost_usd` from the gate's usage, so the proof prices itself whole: the five calibration runs
plus the clean clip run.

### The console, right after

```
$ curl https://airlock-console-771466810465.us-central1.run.app/api/health      (00:24:51 UTC)
ok true
  rights      healthy  error_rate_15m 0  seconds_since_success 106  calibration_catches_7d 4
  claim       healthy  error_rate_15m 0  seconds_since_success 139  calibration_catches_7d 5
  brand       healthy  error_rate_15m 0  seconds_since_success 141  calibration_catches_7d 4
  provenance  healthy  error_rate_15m 0  seconds_since_success 151  calibration_catches_7d 8

$ curl https://airlock-console-771466810465.us-central1.run.app/api/stats       (00:24:52 UTC)
{"ok":true,"mock":false,"checked_7d":51,"passed_7d":27,"blocked_7d":24,"incidents_7d":23,"gates_calibrated":4,"gates_total":4,"cost_per_check_usd_7d":0.09971690196078431,"error":null,"read_at":"2026-09-02T00:24:52.483Z"}
```

Four gates calibrated, and the proof's own series on the stack, read through the Prometheus
datasource: `sum by (outcome) (sum_over_time(airlock_daily_proof_total[1d]))` answered
`{outcome="pass"} 1`.

### Execution 2, from the scheduler (`gcloud scheduler jobs run airlock-daily-proof --location us-central1`, 00:24:59 UTC)

The scheduler as described after the run:

```
name: projects/airlock-agentic-cinema/locations/us-central1/jobs/airlock-daily-proof
schedule: 0 */12 * * *
timeZone: Etc/UTC
state: ENABLED
scheduleTime: '2026-09-02T12:00:01.960792Z'
httpTarget:
  httpMethod: POST
  uri: https://run.googleapis.com/v2/projects/airlock-agentic-cinema/locations/us-central1/jobs/airlock-daily-proof:run
  oauthToken:
    serviceAccountEmail: daily-proof-scheduler@airlock-agentic-cinema.iam.gserviceaccount.com
    scope: https://www.googleapis.com/auth/cloud-platform
```

A second execution appeared 22 s after the trigger and completed:

```
$ gcloud run jobs executions list --job=airlock-daily-proof --region us-central1
EXECUTION                  COMPLETION_TIME              SUCCEEDED_COUNT  FAILED_COUNT  CREATION_TIMESTAMP
airlock-daily-proof-28c9f  2026-09-02T00:29:38.753566Z  1                              2026-09-02T00:25:21.283083Z
airlock-daily-proof-gqt9f  2026-09-02T00:23:19.344282Z  1                              2026-09-02T00:18:54.247176Z
```

Its log, the lines that decide:

```
00:27:19  inputs: 6 downloaded (...)
00:27:58  rights      CAUGHT   37101 ms  real trademark not cleared, faces without release  ->  BLOCK ['registry:brands:not_cleared', 'registry:faces:no_release']
00:27:58  claim       CAUGHT   17035 ms  expert endorsement with no substantiation  ->  BLOCK ['16 CFR 255.3', 'ASA A26-1337640 (CAP 3.7)']
00:27:58  brand       CAUGHT   16732 ms  forbidden red banner and urgency copy  ->  BLOCK ['charter:exclusions', 'charter:palette']
00:27:58  provenance  CAUGHT     543 ms  manifest stripped  ->  BLOCK ['airlock:provenance:manifest-required']
00:27:58  provenance  CAUGHT     583 ms  signed copy with one byte flipped  ->  BLOCK ['airlock:provenance:signature-valid']
          [   3.3s] provenance_gate  PASS      216 ms
          [  11.6s] brand_gate       PASS     8759 ms
          [  16.1s] claim_gate       PASS    13471 ms
          [  84.6s] rights_gate      PASS    82085 ms  cleared brand(s): Nimbus; no unreleased face, no explicit content
          [  87.2s] verdict          grafana  rights      healthy, last success 3 s ago; caught 5 injected defect(s) in 7d
          [  88.3s] verdict          grafana  claim       healthy, last success 73 s ago; caught 6 injected defect(s) in 7d
          [  89.7s] verdict          grafana  brand       healthy, last success 79 s ago; caught 5 injected defect(s) in 7d
          [  90.9s] verdict          grafana  provenance  healthy, last success 88 s ago; caught 10 injected defect(s) in 7d
00:29:33  [  91.8s] verdict          VERDICT PASS (content) needs_human=False annotation=54 6432 ms
                                     all 4 gates PASS, healthy and calibrated
00:29:35  {"outcome": "pass", "verdict": "PASS", "annotation_id": 54, "cost_usd": 1.011693, "calibration_cost_usd": 0.50653, "clean_clip_cost_usd": 0.505163, "gates": {"brand": "CAUGHT", "claim": "CAUGHT", "provenance": "CAUGHT", "rights": "CAUGHT"}, "elapsed_s": {"calibration": 42.0, "clean_clip": 92.1, "inputs": 2.0}}
00:29:35  Container called exit(0).
```

After it, `sum by (outcome) (sum_over_time(airlock_daily_proof_total[1d]))` answered
`{outcome="pass"} 2`. The rights gate took 45 s on the clean clip in execution 1 and 82 s in
execution 2, the Video Intelligence variance already measured in M6a; the 1800 s task timeout
leaves room for the 458 s maximum seen there.

### What one proof costs

Read from the two verdict events and the calibration rows, at list price (`pricing.yaml`, free
quotas not netted): 1.0116 USD and 1.0117 USD per proof. Of that, 1.00 USD is Video Intelligence
(two started minutes, the 30 s Crest excerpt in the calibration and the 8 s clean clip, at 0.50
USD per minute over the four features) and about 0.012 USD is Gemini (the claim and brand gates
twice, 0.0047 and 0.0016 in the calibration, 0.0040 and 0.0012 on the clean clip, read from the
gate events in Loki); provenance costs nothing.

Two proofs a day from 2026-09-02 to 2026-10-19, the day the credit expires: 47 days, 94 proofs,
95.1 USD at list price. The Video Intelligence part of it, 94.0 USD, stays inside the monthly free
quota: 116 minutes per feature in September (29 days) and 76 in October (19 days), against 1000
free minutes per feature per month, so what the bill will carry is the Gemini part, about 1.1 USD
over the period, plus the Cloud Run job itself (about 4 minutes of one vCPU and 2 GiB per proof,
inside the Cloud Run free tier) and one Cloud Scheduler job (three are free per billing account).
The credit read on 2026-08-29 stood at 85.50 EUR; the proof does not threaten it, and the billing
cap of the "Cost and the cap" section stays the guard either way.

### Left as follow-ups, on purpose

- A dashboard panel for `airlock_daily_proof_total` (pass and fail per day): the metric is pushed,
  the panel is not drawn yet.
- `scripts/demo_prep.sh` keeps calling `airlock.calibrate` in step 2 by default (fast, no Agent
  Engine run) and names the job in its heading; `--proof` runs `airlock.daily_proof` in its place,
  the same module the job runs. Chosen so a recording-day preparation stays under a minute unless
  the full proof is wanted.
- Whether two metric pushes a day keep the Grafana Cloud free stack from pausing is not measured;
  the proof runs whether the stack is awake or not (an Influx push to a paused stack would fail
  and the proof would record that failure).

## M6 first pass: the video placeholder and the Devpost draft (2026-09-02)

Two outward actions on Dylan's own accounts, authorised the same day, so that the submission
carries a video link and a project page before the final take exists.

**YouTube.** Channel "Dylan Merigaud" (@dylanmerigaudpro, UC2Yns3jvybFGmPemTd4z3vA), signed in
already in Arc. `video/out/airlock-draft-5-synthetic-voice.mp4` (151.3 s, 43.7 MB) uploaded through
Studio's dialog: title "Airlock: ship or block a generated asset, on proof (Agentic Cinema 2026,
Grafana Labs track)", the description from `docs/DEVPOST.md` (console, public dashboard, repository,
the stack, the synthetic narration named), audience "not made for kids", video language English,
visibility Unlisted, everything else default. The English SRT went in as a subtitle track through
Video elements > Subtitles > Upload file (with timing): the editor read the 19 cues back at the
right times and the row shows "English by you", on top of the burned-in subtitles. Checks:
"Checks complete. No issues found." (copyright included) before the save. The watch page shows the
title, the Unlisted badge and 2:31 (the player reports 151.341 s).

Video: https://youtu.be/xWJ0nMu5cqM

**Devpost.** Logged in as @DylanMerigaud. A draft "Untitled" (1/5 steps) already existed under My
projects, so it was filled rather than a second one created. Project overview: name Airlock, the
tagline of `docs/DEVPOST.md` (146 of 200 characters), thumbnail
`docs/img/console-v3-crest-block-2026-08-29.png`. Project details: the four story sections (What
it does, How I built it, Challenges, Accomplishments) verbatim as one Markdown field, the 17
"Built With" tags one by one, three "Try it out" links (console, repository, public dashboard),
the video link above; the image gallery kept the same screenshot. Additional info: Individual,
organisation N/A, not a government employee, Canada province N/A, project New (after 2026-07-27),
partner track Grafana, team of 1, repository and hosted URLs, the Google Cloud products and the
other tools listed, N/A on the IBM, Parallel, Clickhouse and Replit questions, the IBM marketing
opt-in left unticked. Saved as draft, 3/5 steps done; the Submit page was reached and not clicked.

Draft: https://devpost.com/software/airlock-s2kidr (Devpost shows it as "incomplete submission")

`check.py --type submission docs/DEVPOST.md`:

```
PASS  G17 zero em-dash / en-dash
PASS  G14 section 'what it does'  (216 mots)
PASS  G14 section 'how i built it'  (238 mots)
PASS  G14 section 'challenges'  (178 mots)
PASS  G14 section 'built with'  (17 mots)
PASS  G13 probleme avant techno
PASS  G16 au moins un chiffre  (15 minutes, 7 days, 48 s, 8 s)
PASS  G20 nom du projet  (Airlock)
PASS  G19 exigences du track  (8 cochees)

RESULTAT: PASS mecanique
```

Open: the final video with Dylan's voice (M5), which replaces the draft at the same YouTube link or
at a new one written back into `docs/DEVPOST.md` and the Devpost form; two mandatory Devpost
fields only Dylan can answer (country of residence, first time using Grafana tools), which is why
the Additional info step is not ticked; the Submit click on 2026-09-08, after which Devpost still
allows edits until the deadline. Devpost's reminder asks for a "publicly visible" video: Unlisted
is viewable by anyone with the link, which is what the judges get; switching it to Public is one
radio button on the video's Visibility page if the rules reading demands it.

## Rights gate latency: one operation or four (2026-09-02, 00:36 to 00:45 UTC)

The judge's whole wait is the rights gate, and the rights gate is Video Intelligence. Question:
does one `annotate_video` call with four features wait longer than four parallel calls with one
feature each? Script in the session scratchpad (`vi_latency.py`, pure measurement, no telemetry),
three repetitions, interleaved, strictly one configuration at a time, nothing else running on the
project's Video Intelligence quota.

```
clip        configuration         n   min    median  max     (wall seconds)
clean 8 s   one op, 4 features    3   28.3   33.1    51.1
clean 8 s   four ops, 1 feature   3   25.7   28.5    63.8
Crest 30 s  one op, 4 features    3   43.8   49.0    56.6
Crest 30 s  four ops, 1 feature   3   46.5   49.6    55.1
```

Per feature in the four-op runs: on the 30 s excerpt logo recognition is the long pole every time
(55.1, 49.6, 46.5 s) while faces, text and explicit content finish in 16 to 34 s; on the 8 s clip
the four features take 13 to 29 s except one text detection at 63.8 s. So the service already runs
the features side by side, the split buys nothing, and the spread on the same clip (28 to 51 s
for one op on 8 s) is the service's own. Decision: no change to `airlock/gates/rights.py`; the
console shows an elapsed counter with the measured range on a running gate instead (console
section below). The 173 s seen at 23:58 UTC was concurrency: the cold judge's Crest run and this
session's clean run were on Video Intelligence at the same time, the pattern measured on
2026-08-28 (59 s alone, 598 s with three jobs). Judges testing at the same moment will see it;
the `Try it` paragraph says one to three minutes.
