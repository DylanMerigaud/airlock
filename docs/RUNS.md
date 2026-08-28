# Runs: the proof of every milestone

One block per run: the command, its output (trimmed to what proves the step), and the ids and
URLs a reader can check. The cockpit reads this file; nothing here is retyped by hand.

## M1: the Grafana loop, end to end

Status: in progress (started 2026-08-28).

Track decision: Grafana Labs (Airlock v2). The kill criterion switches to ClickHouse (Falsework)
only if the Agent Engine run cannot reach mcp-grafana on Cloud Run or cannot write the annotation
after the auth options are exhausted. Not triggered.

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
