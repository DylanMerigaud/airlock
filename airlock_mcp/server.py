"""MCP server exposing Airlock's four gates as tools over streamable HTTP.

Each tool builds an Asset from a GCS URI and runs the matching gate through
airlock.gates.base.run_gate, so the same telemetry (Grafana counters and events) that a pipeline
run pushes also flows from a tool call. Inbound auth is a single bearer: every request other than
GET /healthz must carry ``Authorization: Bearer <AIRLOCK_MCP_SERVER_TOKEN>`` or gets a 401.

    AIRLOCK_MCP_SERVER_TOKEN=... python -m airlock_mcp.server
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor
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
from airlock.gates import brand, claim, provenance, rights
from airlock.gates.base import GATES, Asset, GateFn, GateResult, run_gate
from airlock.verdict import promql_questions

TOKEN_ENV = "AIRLOCK_MCP_SERVER_TOKEN"
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FTC_PATH = REPO_ROOT / "rules" / "ftc-16-cfr-255.md"
ASA_PATH = REPO_ROOT / "rules" / "asa-rulings.md"

CHECKS: dict[str, tuple[GateFn, str]] = {
    "rights": (rights.check, rights.SOURCE_OF_TRUTH),
    "claim": (claim.check, claim.SOURCE_OF_TRUTH),
    "brand": (brand.check, brand.SOURCE_OF_TRUTH),
    "provenance": (provenance.check, provenance.SOURCE_OF_TRUTH),
}

# FastMCP's default DNS-rebinding guard only accepts a Host header of localhost or 127.0.0.1
# (measured 2026-08-28: Cloud Run's own hostname got 421 "Invalid Host header"). The bearer
# middleware below is this server's real access control, so that guard is turned off rather than
# chasing the deployed hostname through it.
mcp = FastMCP("airlock", transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


def _asset_from_uri(gcs_uri: str) -> Asset:
    return Asset(asset_id=pathlib.Path(gcs_uri).stem, path="", gcs_uri=gcs_uri)


def _run_gate_on_uri(gate: str, gcs_uri: str) -> dict[str, Any]:
    fn, source = CHECKS[gate]
    result: GateResult = run_gate(gate, fn, _asset_from_uri(gcs_uri), source)
    return result.to_dict()


@mcp.tool()
def check_rights(gcs_uri: str) -> dict:
    """Run the rights gate on a GCS asset: the Video Intelligence API detects logos, faces, text
    and explicit content, checked against rights-registry.yaml. Blocks on any brand the registry
    does not clear, any face with no release on file, or explicit content at or above the
    configured likelihood."""
    return _run_gate_on_uri("rights", gcs_uri)


@mcp.tool()
def check_claim(gcs_uri: str) -> dict:
    """Run the claim gate on a GCS asset: gemini-2.5-pro extracts every spoken or on-screen claim
    with timestamps, and a deterministic rule maps each one to its FTC section and ASA precedent.
    Blocks when a regulated claim (efficacy, health, endorsement, comparative, superlative) has no
    substantiation on file."""
    return _run_gate_on_uri("claim", gcs_uri)


@mcp.tool()
def check_brand(gcs_uri: str) -> dict:
    """Run the brand gate on a GCS asset: gemini-2.5-flash reads it against charter.yaml (palette,
    tone, mandatory mention, exclusions), and a deterministic rule checks the findings. Blocks when
    the mandatory wordmark is missing, an exclusion is violated, or the tone, palette or typography
    strays from the charter."""
    return _run_gate_on_uri("brand", gcs_uri)


@mcp.tool()
def check_provenance(gcs_uri: str) -> dict:
    """Run the provenance gate on a GCS asset: c2pa-python reads any C2PA manifest and verifies its
    signature against trust/trust-anchors.pem. Blocks when there is no manifest, the signature does
    not validate, or the signer is not on the trust list."""
    return _run_gate_on_uri("provenance", gcs_uri)


@mcp.tool()
def check_all(gcs_uri: str) -> dict:
    """Run all four gates on a GCS asset at once, in a thread pool, and return each gate's result
    with the wall-clock time. Blocks on nothing itself; it only reports what the four individual
    gates decide."""
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=len(GATES)) as pool:
        futures = {gate: pool.submit(_run_gate_on_uri, gate, gcs_uri) for gate in GATES}
        gate_results = [futures[gate].result() for gate in GATES]
    return {"gates": gate_results, "wall_ms": int((time.time() - t0) * 1000)}


@mcp.tool()
def verdict_rules() -> str:
    """Return the docstring of airlock.verdict, the deterministic PASS or BLOCK rules over gate
    results and Grafana health, plus the PromQL questions asked about the rights gate. Reads no
    live data and blocks nothing; it only describes what the verdict will ask."""
    questions = promql_questions("rights")
    return (verdict_module.__doc__ or "").strip() + "\n\nPromQL questions asked for gate 'rights':\n" + json.dumps(questions, indent=2)


def _headings(path: pathlib.Path, marker: str = "## ") -> list[str]:
    return [line.removeprefix(marker).strip() for line in path.read_text().splitlines() if line.startswith(marker)]


@mcp.tool()
def list_rules() -> dict:
    """Read rules/ftc-16-cfr-255.md and rules/asa-rulings.md from disk and return the FTC section
    headings and the two ASA ruling references the claim gate cites. Blocks nothing; it is a
    reference lookup for an agent preparing a claim review."""
    return {"ftc_sections": _headings(FTC_PATH), "asa_rulings": _headings(ASA_PATH)[:2]}


class BearerAuthMiddleware:
    """Plain ASGI middleware: everything but GET /healthz needs Authorization: Bearer <token>.

    Written at the ASGI level, not as BaseHTTPMiddleware, because the streamable HTTP transport
    holds a request open to stream server-to-client messages; wrapping it in a buffering
    middleware would break that.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == "/healthz":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("latin-1")
        if auth != f"Bearer {self.token}":
            await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def create_app() -> Starlette:
    """Build the Starlette app: the bearer middleware, GET /healthz, and the MCP app at /mcp.

    Refuses to build when AIRLOCK_MCP_SERVER_TOKEN is unset, so the server never comes up silently
    open.
    """
    token = os.environ.get(TOKEN_ENV)
    if not token:
        raise RuntimeError(f"{TOKEN_ENV} is not set; refusing to start a server with no bearer to enforce")

    # FastMCP memoizes one StreamableHTTPSessionManager on first streamable_http_app() call, and it
    # can only .run() once ever. create_app() runs exactly once in production; tests build several
    # app instances from this same module-level mcp, so each needs its own fresh manager.
    mcp._session_manager = None

    async def healthz(request: Request) -> JSONResponse:
        tools = await mcp.list_tools()
        return JSONResponse({"ok": True, "tools": [t.name for t in tools]})

    @asynccontextmanager
    async def lifespan(app: Starlette):
        async with mcp.session_manager.run():
            yield

    return Starlette(
        routes=[Route("/healthz", healthz, methods=["GET"]), Mount("/", app=mcp.streamable_http_app())],
        middleware=[Middleware(BearerAuthMiddleware, token=token)],
        lifespan=lifespan,
    )


def main() -> None:
    if not os.environ.get(TOKEN_ENV):
        sys.exit(f"{TOKEN_ENV} is not set; refusing to start (set it to the bearer clients must send)")
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), log_level="info")


if __name__ == "__main__":
    main()
