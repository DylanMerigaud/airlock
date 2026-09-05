"""VerdictAgent's own failure path: when Grafana cannot be reached at all (the toolset itself fails
before any question is asked), the verdict is ERROR/instrument error in state, not a raised exception
that would strand the run before the investigator and the escalation ever see it. No cloud call: the
toolset is a fake that raises."""

from __future__ import annotations

import json

import pytest
from google.adk.agents.invocation_context import InvocationContext
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.sessions.session import Session
from google.genai import types

from agents.pipeline import agent as pipeline
from agents.pipeline.agent import GATES, STATE_GATE, STATE_VERDICT, VerdictAgent

RUN = "e-verdict-fail"


class RaisingToolset:
    """Stands in for make_grafana_toolset: get_tools raises before any Grafana question is asked."""

    def __init__(self):
        self.closed = False

    async def get_tools(self, tool_ctx):
        raise RuntimeError("Grafana Cloud was starting, waited 180 s: getDataSources (status 503)")

    async def close(self):
        self.closed = True


def make_ctx() -> InvocationContext:
    state = {STATE_GATE.format(g): {"status": "PASS", "reasons": ["ok"], "rule_ids": []} for g in GATES}
    session = Session(id="s1", app_name="airlock", user_id="u1", state=state)
    return InvocationContext(
        session_service=InMemorySessionService(),
        invocation_id=RUN,
        agent=VerdictAgent(name="verdict"),
        session=session,
        user_content=types.Content(role="user", parts=[types.Part(text="gs://bucket/nimbus-clean-clip.mp4")]),
    )


@pytest.mark.asyncio
async def test_a_toolset_that_cannot_be_reached_becomes_an_error_verdict_not_a_raised_exception(monkeypatch):
    monkeypatch.delenv("GRAFANA_INFLUX_URL", raising=False)  # push_verdict_sample must stay a no-op
    toolset = RaisingToolset()
    monkeypatch.setattr(pipeline, "make_grafana_toolset", lambda tool_filter: toolset)

    events = [e async for e in VerdictAgent(name="verdict")._run_async_impl(make_ctx())]

    assert len(events) == 1
    payload = json.loads(events[0].content.parts[0].text)
    assert payload["status"] == "ERROR" and payload["motive"] == "instrument error" and payload["needs_human"] is True
    assert "RuntimeError" in payload["reasons"][0]
    delta = events[0].actions.state_delta[STATE_VERDICT]
    assert delta["status"] == "ERROR" and delta["needs_human"] is True
    assert delta["run_id"] == RUN and delta["asset_id"]
    assert len(delta["gates"]) == len(GATES)  # the investigator still gets a gate line per gate
    assert toolset.closed  # the finally branch runs even when get_tools raised
