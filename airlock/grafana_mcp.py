"""The Grafana MCP toolset every agent uses.

Points at the mcp-grafana server deployed on Cloud Run (streamable HTTP). The
server enforces a bearer of its own (MCP_GRAFANA_SERVER_TOKEN); the agent sends
it from AIRLOCK_MCP_TOKEN, which comes from Secret Manager on Agent Engine and
from a local .env when run with ``adk run``.
"""

from __future__ import annotations

import json
import os
from typing import Any

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

DEFAULT_TOOLS = [
    "list_datasources",
    "query_prometheus",
    "create_annotation",
    "get_annotations",
    "create_incident",
    "list_incidents",
    "get_dashboard_summary",
]


def _auth_headers(_ctx: ReadonlyContext | None = None) -> dict[str, str]:
    token = os.environ.get("AIRLOCK_MCP_TOKEN", "")
    if not token:
        raise RuntimeError("AIRLOCK_MCP_TOKEN is not set")
    return {"Authorization": f"Bearer {token}"}


def make_grafana_toolset(tool_filter: list[str] | None = None) -> McpToolset:
    url = os.environ.get("AIRLOCK_MCP_URL", "")
    if not url:
        raise RuntimeError("AIRLOCK_MCP_URL is not set")
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(url=url, timeout=30.0, sse_read_timeout=120.0),
        header_provider=_auth_headers,
        tool_filter=tool_filter if tool_filter is not None else DEFAULT_TOOLS,
    )


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
    """The uid of the first Prometheus-type datasource in a list_datasources answer (list or object)."""
    try:
        data = json.loads(datasources_text)
    except json.JSONDecodeError as exc:
        raise LookupError(f"list_datasources did not answer JSON: {datasources_text[:300]!r}") from exc
    if isinstance(data, dict):
        items = data.get("datasources") or data.get("items") or data.get("data") or []
    else:
        items = data
    for ds in items:
        if isinstance(ds, dict) and str(ds.get("type", "")).lower() == "prometheus":
            return ds["uid"]
    raise LookupError(f"no prometheus datasource in the answer: {datasources_text[:300]!r}")
