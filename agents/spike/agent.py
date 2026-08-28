"""M1 spike: one ADK agent, one MCP hop to Grafana, one PromQL query, one annotation.

No LLM in the loop on purpose: the spike measures the network and auth path
from Agent Engine to mcp-grafana on Cloud Run, nothing else. The verdict agent
of M3 keeps this shape (a BaseAgent calling MCP tools directly) and adds the
deterministic rules on top.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.context import Context
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.events.event import Event
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.genai import types

try:
    import airlock as _airlock_pkg  # noqa: F401  (tells us whether extra_packages reached Agent Engine)

    AIRLOCK_PKG_IMPORTABLE = True
except Exception:  # pragma: no cover
    AIRLOCK_PKG_IMPORTABLE = False

SPIKE_EXPR = 'sum(sum_over_time(airlock_gate_runs_total{gate="spike"}[24h]))'


def _auth_headers(_ctx: ReadonlyContext | None = None) -> dict[str, str]:
    token = os.environ.get("AIRLOCK_MCP_TOKEN", "")
    if not token:
        raise RuntimeError("AIRLOCK_MCP_TOKEN is not set")
    return {"Authorization": f"Bearer {token}"}


def tool_text(result: Any) -> str:
    """Flatten an MCP tool result (dict with content parts, or a bare value) to text."""
    if isinstance(result, dict):
        parts = result.get("content")
        if isinstance(parts, list):
            return "\n".join(str(p.get("text", p)) if isinstance(p, dict) else str(p) for p in parts)
        if "result" in result:
            return tool_text(result["result"])
        return json.dumps(result)
    if isinstance(result, list):
        return "\n".join(tool_text(x) for x in result)
    return str(result)


def pick_prometheus_uid(datasources_text: str) -> str:
    """Return the uid of the first Prometheus-type datasource in a list_datasources answer."""
    try:
        data = json.loads(datasources_text)
    except json.JSONDecodeError as exc:
        raise LookupError(f"list_datasources did not answer JSON: {datasources_text[:300]!r}") from exc
    items = data if isinstance(data, list) else data.get("datasources") or data.get("items") or []
    for ds in items:
        if str(ds.get("type", "")).lower() == "prometheus":
            return ds["uid"]
    raise LookupError("no prometheus datasource in the answer")


class SpikeAgent(BaseAgent):
    """Lists datasources, runs one PromQL query, writes one annotation, reports each step."""

    def _event(self, ctx: InvocationContext, text: str) -> Event:
        return Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(role="model", parts=[types.Part(text=text)]),
        )

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        started = time.time()
        mcp_url = os.environ.get("AIRLOCK_MCP_URL", "")
        dashboard_uid = os.environ.get("AIRLOCK_DASHBOARD_UID", "airlock-gates")
        yield self._event(ctx, f"spike start: mcp={mcp_url} airlock_pkg_importable={AIRLOCK_PKG_IMPORTABLE}")
        if not mcp_url:
            yield self._event(ctx, "spike ERROR: AIRLOCK_MCP_URL is not set")
            return

        toolset = McpToolset(
            connection_params=StreamableHTTPConnectionParams(url=mcp_url, timeout=30.0, sse_read_timeout=120.0),
            header_provider=_auth_headers,
            tool_filter=["list_datasources", "query_prometheus", "create_annotation"],
        )
        tool_ctx = Context(invocation_context=ctx)
        try:
            tools = {t.name: t for t in await toolset.get_tools(tool_ctx)}
            yield self._event(ctx, f"mcp tools reachable: {sorted(tools)}")

            ds_raw = await tools["list_datasources"].run_async(args={"type": "prometheus"}, tool_context=tool_ctx)
            prom_uid = pick_prometheus_uid(tool_text(ds_raw))
            yield self._event(ctx, f"prometheus datasource uid: {prom_uid}")

            q_raw = await tools["query_prometheus"].run_async(
                args={"datasourceUid": prom_uid, "expr": SPIKE_EXPR, "queryType": "instant", "endTime": "now"},
                tool_context=tool_ctx,
            )
            q_text = tool_text(q_raw)
            yield self._event(ctx, f"promql {SPIKE_EXPR} => {q_text[:800]}")

            now_ms = int(time.time() * 1000)
            a_raw = await tools["create_annotation"].run_async(
                args={
                    "dashboardUid": dashboard_uid,
                    "time": now_ms,
                    "text": f"spike ok: {SPIKE_EXPR} answered from {os.environ.get('AIRLOCK_RUNTIME', 'local')}",
                    "tags": ["airlock", "spike", os.environ.get("AIRLOCK_RUNTIME", "local")],
                },
                tool_context=tool_ctx,
            )
            yield self._event(ctx, f"annotation created: {tool_text(a_raw)[:400]}")
            yield self._event(ctx, f"spike done in {int((time.time() - started) * 1000)} ms")
        except Exception as exc:  # the spike must say what failed, never pass silently
            yield self._event(ctx, f"spike ERROR: {type(exc).__name__}: {exc}")
            raise
        finally:
            await toolset.close()


root_agent = SpikeAgent(name="airlock_spike", description="M1 spike: PromQL query and annotation through mcp-grafana")
