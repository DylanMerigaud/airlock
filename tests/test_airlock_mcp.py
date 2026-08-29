import asyncio

import pytest
from starlette.testclient import TestClient

from airlock_mcp.server import TOKEN_ENV, create_app, mcp

EXPECTED_TOOLS = {"check_rights", "check_claim", "check_brand", "check_provenance", "check_all", "verdict_rules", "list_rules"}


def test_tool_list_has_the_seven_tools():
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == EXPECTED_TOOLS


def test_create_app_refuses_without_a_token(monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    with pytest.raises(RuntimeError, match=TOKEN_ENV):
        create_app()


def test_mcp_endpoint_401s_without_a_bearer(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "test-token")
    with TestClient(create_app()) as client:
        resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert resp.status_code == 401


def test_mcp_endpoint_401s_with_the_wrong_bearer(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "test-token")
    with TestClient(create_app()) as client:
        resp = client.post("/mcp", json={}, headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401


def test_healthz_is_open_and_lists_tools(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "test-token")
    with TestClient(create_app()) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert set(body["tools"]) == EXPECTED_TOOLS
