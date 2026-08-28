"""The Grafana MCP toolset every agent uses.

Points at the mcp-grafana server deployed on Cloud Run (streamable HTTP). The
server enforces a bearer of its own (MCP_GRAFANA_SERVER_TOKEN); the agent sends
it from AIRLOCK_MCP_TOKEN, which comes from Secret Manager on Agent Engine and
from a local .env when run with ``adk run``.
"""

from __future__ import annotations

import os

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
