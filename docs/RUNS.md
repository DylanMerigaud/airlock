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
