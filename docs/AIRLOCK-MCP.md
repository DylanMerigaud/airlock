# airlock-mcp: Airlock's four gates as MCP tools

`airlock_mcp/server.py` wraps `airlock.gates.{rights,claim,brand,provenance}` in a
`FastMCP("airlock")` server, served over the streamable HTTP transport at `/mcp`. Every tool
runs its gate through `airlock.gates.base.run_gate`, so a tool call pushes the same Grafana
counters and events a pipeline run does. Inbound auth is a single bearer
(`AIRLOCK_MCP_SERVER_TOKEN`); a request without `Authorization: Bearer <token>` gets 401,
except `GET /healthz` which is open.

## Tools

| tool | reads | blocks (reported by the gate, not the tool) |
|---|---|---|
| `check_rights(gcs_uri)` | Video Intelligence (logos, faces, text, explicit) against `rights-registry.yaml` | an unlicensed brand, an unreleased face, explicit content |
| `check_claim(gcs_uri)` | gemini-2.5-pro's claim extraction against `rules/ftc-16-cfr-255.md` and `rules/asa-rulings.md` | a regulated claim with no substantiation on file |
| `check_brand(gcs_uri)` | gemini-2.5-flash's read of the asset against `charter.yaml` | missing wordmark, an exclusion, off-charter tone or palette |
| `check_provenance(gcs_uri)` | the C2PA manifest against `trust/trust-anchors.pem` | no manifest, an invalid signature, an untrusted signer |
| `check_all(gcs_uri)` | the four gates above, in a thread pool | nothing itself; reports what the four decide, plus `wall_ms` |
| `verdict_rules()` | the docstring of `airlock.verdict` plus the PromQL questions for the rights gate | nothing; a reference call |
| `list_rules()` | the FTC section headings and the two ASA references cited by the claim gate | nothing; a reference call |

Every `check_*` tool takes one argument, `gcs_uri` (a `gs://` URI), and returns
`GateResult.to_dict()`: `gate`, `status` (`PASS`, `BLOCK` or `ERROR`), `reasons`, `evidence`,
`rule_ids`, `elapsed_ms`, `source_of_truth`.

## Connecting

A Claude Desktop or Cursor style `mcpServers` entry (the bearer goes in a custom header, since
neither client reads Secret Manager or the keychain):

```json
{
  "mcpServers": {
    "airlock": {
      "url": "https://airlock-mcp-771466810465.us-central1.run.app/mcp",
      "headers": { "Authorization": "Bearer <AIRLOCK_MCP_SERVER_TOKEN>" }
    }
  }
}
```

The `mcp` Python client, streamable HTTP:

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

url = "https://airlock-mcp-771466810465.us-central1.run.app/mcp"
headers = {"Authorization": "Bearer <AIRLOCK_MCP_SERVER_TOKEN>"}

async with streamablehttp_client(url, headers=headers) as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("check_provenance", {"gcs_uri": "gs://bucket/clip.mp4"})
```

`scripts/airlock_mcp_client.py` is this same recipe, wired to the keychain entry
`airlock-mcp-server-token` and the two demo assets:

```
uv run python scripts/airlock_mcp_client.py            # the deployed URL
uv run python scripts/airlock_mcp_client.py --local    # http://127.0.0.1:8080/mcp
uv run python scripts/airlock_mcp_client.py --url <u>  # any other URL
```

## Running locally

```
AIRLOCK_MCP_SERVER_TOKEN=x scripts/with_env.sh uv run python -m airlock_mcp.server
```

`scripts/with_env.sh` loads `.env.local` and pulls the Grafana tokens from the keychain, so gate
telemetry pushes work even off the deployed service. `AIRLOCK_MCP_SERVER_TOKEN` is not one of the
tokens `with_env.sh` fetches (it is the server's own bearer, not a Grafana credential); set it
directly, or generate one and store it in the keychain the way
`infra/airlock-mcp/deploy.sh` does. Without it set, the server refuses to start and says so.
The server listens on `0.0.0.0:$PORT` (default 8080); `GET /healthz` and `/mcp` are both local at
that point.

## Deploying

```
bash infra/airlock-mcp/deploy.sh
```

Idempotent: generates and stores `airlock-mcp-server-token` in the keychain and in Secret Manager
if either is missing, creates the Artifact Registry repository `airlock` in `us-central1` if
missing, builds `Dockerfile.mcp` with Cloud Build, and deploys to Cloud Run as `airlock-mcp`
(`--allow-unauthenticated` at the network level, closed at the MCP level by the bearer). Prints
the service URL and its `/mcp` and `/healthz` paths on completion.

Deployed URL (`us-central1`): `https://airlock-mcp-771466810465.us-central1.run.app`.

## A platform note on `/healthz`

`GET /healthz` works locally and in `docker run` (verified both ways, see `docs/RUNS.md`), but on
Cloud Run specifically a request to that exact path gets a Google-branded 404 that never reaches
the container (confirmed empirically: zero log lines for it, `POST`/`GET` to any other path do
show up). Cloud Run's frontend reserves `/healthz` for its own internal probing and intercepts it
ahead of the application; this is a documented platform behavior, not a bug in this server. The
route stays at `/healthz` in the code, as specified, since it works everywhere except this one
host; a health check against the deployed service should hit `/mcp` (401 without a bearer, which
still proves the service is up) instead.
