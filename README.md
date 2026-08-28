# Airlock

Studios ship dozens of generated assets a week, and nobody can prove which one was checked, by
which rule, and whether the check itself was working.

Airlock runs a generated media asset through four gates (rights, claim, brand, provenance), then a
verdict agent asks Grafana, through MCP, whether each gate is healthy and has already caught a real
injected defect before it is allowed to say PASS. The verdict is written back to Grafana as an
annotation; a BLOCK that needs a human opens an incident.

Built for Agentic Cinema (Google Cloud, Grafana Labs track), 2026-08-28 to 2026-09-09. Gemini on
Vertex AI, ADK, Vertex AI Agent Engine, mcp-grafana on Cloud Run, Video Intelligence API, C2PA.

Status: M1 spike in progress. Proofs of every milestone: `docs/RUNS.md`. Synthetic inputs, when
any: `SYNTHETIC.md`.

## Layout

- `airlock/` gates, telemetry push, the Grafana MCP toolset
- `agents/<name>/` one ADK agent folder each, deployable with `adk deploy agent_engine`
- `infra/` Google Cloud bootstrap, Secret Manager loader, mcp-grafana on Cloud Run
- `scripts/` Grafana dashboard bootstrap, metric push, Agent Engine query
- `tests/` pytest on every deterministic rule

## Run the tests

```
uv sync
uv run pytest -q
```

License: Apache-2.0.
