"""airlock-mcp: the seven tools, the bearer, the open health route, and tools that do not hold the event loop."""

import asyncio
import time

import pytest
from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

from airlock_mcp import server as server_module
from airlock_mcp.server import HEALTH_PATH, TOKEN_ENV, build_mcp, create_app

EXPECTED_TOOLS = {"check_rights", "check_claim", "check_brand", "check_provenance", "check_all", "verdict_rules", "list_rules"}


@pytest.fixture
def mcp() -> FastMCP:
    """A fresh server per test: FastMCP's session manager runs once per instance, so no test shares one."""
    return build_mcp()


def test_tool_list_has_the_seven_tools(mcp):
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == EXPECTED_TOOLS


def test_create_app_refuses_without_a_token(monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    with pytest.raises(RuntimeError, match=TOKEN_ENV):
        create_app()


def test_mcp_endpoint_401s_without_a_bearer(monkeypatch, mcp):
    monkeypatch.setenv(TOKEN_ENV, "test-token")
    with TestClient(create_app(mcp)) as client:
        resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert resp.status_code == 401


def test_mcp_endpoint_401s_with_the_wrong_bearer(monkeypatch, mcp):
    monkeypatch.setenv(TOKEN_ENV, "test-token")
    with TestClient(create_app(mcp)) as client:
        resp = client.post("/mcp", json={}, headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401


def test_health_is_open_and_lists_tools(monkeypatch, mcp):
    monkeypatch.setenv(TOKEN_ENV, "test-token")
    with TestClient(create_app(mcp)) as client:
        resp = client.get(HEALTH_PATH)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert set(body["tools"]) == EXPECTED_TOOLS
        assert HEALTH_PATH == "/health"
        assert client.get("/healthz").status_code == 401  # only the health path is open


def test_two_apps_from_two_servers_both_serve(monkeypatch):
    """The reason for build_mcp(): two apps in one process, each with its own session manager, no private reset."""
    monkeypatch.setenv(TOKEN_ENV, "test-token")
    with TestClient(create_app(build_mcp())) as a, TestClient(create_app(build_mcp())) as b:
        assert a.get(HEALTH_PATH).status_code == 200 and b.get(HEALTH_PATH).status_code == 200


async def test_check_tools_run_the_gate_off_the_event_loop(monkeypatch):
    """Two check_provenance calls whose gate sleeps 0.3 s each finish in about 0.3 s together, not 0.6 s:
    the gate runs in a worker thread and the loop stays free (the blocking-loop defect of 2026-09-05)."""

    def slow_gate(gate: str, gcs_uri: str) -> dict:
        time.sleep(0.3)
        return {"gate": gate, "status": "PASS", "gcs_uri": gcs_uri}

    monkeypatch.setattr(server_module, "_run_gate_on_uri", slow_gate)
    t0 = time.monotonic()
    results = await asyncio.gather(server_module.check_provenance("gs://b/one.mp4"), server_module.check_provenance("gs://b/two.mp4"))
    elapsed = time.monotonic() - t0
    assert [r["gcs_uri"] for r in results] == ["gs://b/one.mp4", "gs://b/two.mp4"]
    assert elapsed < 0.55, f"two 0.3 s gates took {elapsed:.2f} s: they ran one after the other on the loop"


async def test_check_all_runs_the_four_gates_together(monkeypatch):
    def slow_gate(gate: str, gcs_uri: str) -> dict:
        time.sleep(0.2)
        return {"gate": gate, "status": "PASS"}

    monkeypatch.setattr(server_module, "_run_gate_on_uri", slow_gate)
    out = await server_module.check_all("gs://b/x.mp4")
    assert [g["gate"] for g in out["gates"]] == ["rights", "claim", "brand", "provenance"]
    assert out["wall_ms"] < 550
