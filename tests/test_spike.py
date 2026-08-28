import json

import pytest

from agents.spike.agent import pick_prometheus_uid, tool_text


def test_tool_text_flattens_mcp_content_parts():
    raw = {"content": [{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}], "isError": False}
    assert tool_text(raw) == "hello\nworld"


def test_tool_text_passes_strings_through():
    assert tool_text("plain") == "plain"


def test_pick_prometheus_uid_from_list():
    body = json.dumps([{"uid": "loki1", "type": "loki"}, {"uid": "prom1", "type": "prometheus", "name": "grafanacloud-x-prom"}])
    assert pick_prometheus_uid(body) == "prom1"


def test_pick_prometheus_uid_missing_raises():
    with pytest.raises(LookupError):
        pick_prometheus_uid(json.dumps([{"uid": "loki1", "type": "loki"}]))
