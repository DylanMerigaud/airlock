"""MCP server exposing Airlock's four gates as tools over streamable HTTP.

Each tool builds an Asset from a GCS URI and runs the matching gate through
airlock.gates.base.run_gate, so the same telemetry (Grafana counters and events) that a pipeline
run pushes also flows from a tool call. Inbound auth is a single bearer: every request other than
GET /health must carry ``Authorization: Bearer <AIRLOCK_MCP_SERVER_TOKEN>`` or gets a 401.

The tools are async and hand the gate to a worker thread (asyncio.to_thread), the way the pipeline's
gate agents do: a rights check holds Video Intelligence for 30 to 600 s, and before 2026-09-05 the
tools were plain ``def``, which FastMCP runs inline on the event loop, so a second client (even an
initialize) waited for the first tool to return.

    AIRLOCK_MCP_SERVER_TOKEN=... python -m airlock_mcp.server
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import pathlib
import sys
import time
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

import airlock.verdict as verdict_module
from airlock import settings, tracing
from airlock.gates import CHECKS, GATES
from airlock.gates.base import Asset, GateResult, run_gate
from airlock.verdict import promql_questions

TOKEN_ENV = "AIRLOCK_MCP_SERVER_TOKEN"
HEALTH_PATH = "/health"  # not /healthz: Cloud Run's front end answers that path itself and never reaches the container
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FTC_PATH = REPO_ROOT / "rules" / "ftc-16-cfr-255.md"
ASA_PATH = REPO_ROOT / "rules" / "asa-rulings.md"


def _asset_from_uri(gcs_uri: str) -> Asset:
    return Asset(asset_id=pathlib.Path(gcs_uri).stem, path="", gcs_uri=gcs_uri)


def _run_gate_on_uri(gate: str, gcs_uri: str) -> dict[str, Any]:
    fn, source = CHECKS[gate]
    result: GateResult = run_gate(gate, fn, _asset_from_uri(gcs_uri), source)
    return result.to_dict()


async def check_rights(gcs_uri: str) -> dict:
    """Run the rights gate on a GCS asset: the Video Intelligence API detects logos, faces, text
    and explicit content, checked against rights-registry.yaml. Blocks on any brand the registry
    does not clear, any face with no release on file, or explicit content at or above the
    configured likelihood."""
    return await asyncio.to_thread(_run_gate_on_uri, "rights", gcs_uri)


async def check_claim(gcs_uri: str) -> dict:
    """Run the claim gate on a GCS asset: gemini-2.5-pro extracts every spoken or on-screen claim
    with timestamps, and a deterministic rule maps each one to its FTC section and ASA precedent.
    Blocks when a regulated claim (efficacy, health, endorsement, comparative, superlative) has no
    substantiation on file."""
    return await asyncio.to_thread(_run_gate_on_uri, "claim", gcs_uri)


async def check_brand(gcs_uri: str) -> dict:
    """Run the brand gate on a GCS asset: gemini-2.5-flash reads it against charter.yaml (palette,
    tone, mandatory mention, exclusions), and a deterministic rule checks the findings. Blocks when
    the mandatory wordmark is missing, an exclusion is violated, or the tone, palette or typography
    strays from the charter."""
    return await asyncio.to_thread(_run_gate_on_uri, "brand", gcs_uri)


async def check_provenance(gcs_uri: str) -> dict:
    """Run the provenance gate on a GCS asset: c2pa-python reads any C2PA manifest and verifies its
    signature against trust/trust-anchors.pem. Blocks when there is no manifest, the signature does
    not validate, or the signer is not on the trust list."""
    return await asyncio.to_thread(_run_gate_on_uri, "provenance", gcs_uri)


async def check_all(gcs_uri: str) -> dict:
    """Run all four gates on a GCS asset at once, each in a worker thread, and return each gate's
    result with the wall-clock time. Blocks on nothing itself; it only reports what the four
    individual gates decide."""
    t0 = time.time()
    gate_results = await asyncio.gather(*(asyncio.to_thread(_run_gate_on_uri, gate, gcs_uri) for gate in GATES))
    return {"gates": list(gate_results), "wall_ms": int((time.time() - t0) * 1000)}


def verdict_rules() -> str:
    """Return the docstring of airlock.verdict, the deterministic PASS or BLOCK rules over gate
    results and Grafana health, plus the PromQL questions asked about the rights gate. Reads no
    live data and blocks nothing; it only describes what the verdict will ask."""
    questions = promql_questions("rights")
    return (verdict_module.__doc__ or "").strip() + "\n\nPromQL questions asked for gate 'rights':\n" + json.dumps(questions, indent=2)


def _headings(path: pathlib.Path, marker: str = "## ") -> list[str]:
    return [line.removeprefix(marker).strip() for line in path.read_text().splitlines() if line.startswith(marker)]


def list_rules() -> dict:
    """Read rules/ftc-16-cfr-255.md and rules/asa-rulings.md from disk and return the FTC section
    headings and the two ASA ruling references the claim gate cites. Blocks nothing; it is a
    reference lookup for an agent preparing a claim review."""
    return {"ftc_sections": _headings(FTC_PATH), "asa_rulings": _headings(ASA_PATH)[:2]}


TOOLS = (check_rights, check_claim, check_brand, check_provenance, check_all, verdict_rules, list_rules)


def build_mcp() -> FastMCP:
    """A fresh FastMCP with the seven tools registered.

    Built per app rather than once at import: FastMCP creates one StreamableHTTPSessionManager on the
    first streamable_http_app() call and that manager can only run once, so an app needs its own
    server instance (the production process builds one; a test builds one per app, and no private
    attribute is touched).

    FastMCP's default DNS-rebinding guard only accepts a Host header of localhost or 127.0.0.1
    (measured 2026-08-28: Cloud Run's own hostname got 421 "Invalid Host header"). The bearer
    middleware below is this server's real access control, so that guard is turned off rather than
    chasing the deployed hostname through it.
    """
    server = FastMCP("airlock", transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    for fn in TOOLS:
        server.add_tool(fn)
    return server


class BearerAuthMiddleware:
    """Plain ASGI middleware: everything but GET /health needs Authorization: Bearer <token>.

    Written at the ASGI level, not as BaseHTTPMiddleware, because the streamable HTTP transport
    holds a request open to stream server-to-client messages; wrapping it in a buffering
    middleware would break that.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == HEALTH_PATH:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("latin-1")
        # A `!=` comparison on a bearer string returns as soon as it finds a differing byte, so how long the
        # 401 takes leaks how many characters of the guess were right (a timing side channel; third panel,
        # 2026-09-05). hmac.compare_digest always looks at the whole string.
        if not hmac.compare_digest(auth, f"Bearer {self.token}"):
            await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def create_app(server: FastMCP | None = None) -> Starlette:
    """Build the Starlette app: the bearer middleware, GET /health, and the MCP app at /mcp.

    Refuses to build when AIRLOCK_MCP_SERVER_TOKEN is unset, so the server never comes up silently
    open. `server` defaults to a fresh build_mcp(); a test may pass its own.
    """
    token = settings.airlock_mcp_server_token()
    if not token:
        raise RuntimeError(f"{TOKEN_ENV} is not set; refusing to start a server with no bearer to enforce")
    server = server or build_mcp()

    async def health(request: Request) -> JSONResponse:
        tools = await server.list_tools()
        return JSONResponse({"ok": True, "tools": [t.name for t in tools]})

    @asynccontextmanager
    async def lifespan(app: Starlette):
        async with server.session_manager.run():
            yield

    return Starlette(
        routes=[Route(HEALTH_PATH, health, methods=["GET"]), Mount("/", app=server.streamable_http_app())],
        middleware=[Middleware(BearerAuthMiddleware, token=token)],
        lifespan=lifespan,
    )


def main() -> None:
    if not settings.airlock_mcp_server_token():
        sys.exit(f"{TOKEN_ENV} is not set; refusing to start (set it to the bearer clients must send)")
    import uvicorn

    tracing.configure()  # each gate tool call is one span (its own trace) in Tempo when GRAFANA_OTLP_TOKEN is set
    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), log_level="info")


if __name__ == "__main__":
    main()
