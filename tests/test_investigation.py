"""The investigator and the deduplicating escalation: the instruction, the Loki answer as the model reads
it, the budget, the fallback, the incident routing. No cloud call: the LlmAgent is replaced by a fake."""

from __future__ import annotations

import asyncio
import json
from types import MappingProxyType, SimpleNamespace

import pytest
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.models.llm_response import LlmResponse
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.sessions.session import Session
from google.genai import types

from agents.pipeline import agent as pipeline
from agents.pipeline.agent import (
    INVESTIGATION_OUTPUT_KEY,
    INVESTIGATION_TOOL_BUDGET,
    STATE_INVESTIGATION,
    STATE_VERDICT,
    InvestigationAgent,
    InvestigationBudget,
    cited_lines,
    compact_loki_answer,
    fallback_note,
    find_open_incident,
    format_loki_line,
    gates_to_investigate,
    incident_body,
    incident_owner,
    incident_title,
    investigation_kind,
    investigator_instruction,
    loki_lines_from_answer,
    note_kind_line,
    tool_rows,
)

RUN = "e-7f3a"
TS = '"1788566913325404907"'  # 2026-09-05T00:08:33.325Z


def verdict_payload(status="BLOCK", motive="control unavailable", rule_ids=None, gates=None) -> dict:
    return {
        "status": status, "motive": motive, "needs_human": status == "BLOCK", "run_id": RUN, "asset_id": "nimbus-clean-clip",
        "reasons": ["rights: control unavailable (instrument error: TimeoutError: fault injected; seen by Grafana for this run)"],
        "rule_ids": rule_ids or ["airlock:verdict:R1-control-unavailable", "airlock:verdict:instrument-error"],
        "gates": gates or [
            {"gate": "rights", "status": "ERROR", "reason": "TimeoutError: fault injected", "seen_this_run": True, "calibrated": True, "calibration": "caught 12"},
            {"gate": "claim", "status": "PASS", "reason": "ok", "seen_this_run": True, "calibrated": True, "calibration": "caught 12"},
            {"gate": "brand", "status": "PASS", "reason": "ok", "seen_this_run": True, "calibrated": True, "calibration": "caught 12"},
            {"gate": "provenance", "status": "PASS", "reason": "ok", "seen_this_run": True, "calibrated": True, "calibration": "caught 24"},
        ],
    }


def loki_answer(*bodies: dict, with_evidence: bool = False) -> str:
    rows = []
    for b in bodies:
        body = dict(b)
        if with_evidence:
            body["evidence"] = [{"traceback": "x" * 500}]
        rows.append({"timestamp": TS, "line": json.dumps(body), "labels": {"app": "airlock", "gate": body.get("gate", "rights"), "status": body.get("status", "PASS")}})
    return json.dumps({"data": rows, "metadata": {"linesReturned": len(rows)}})


def test_kind_is_root_cause_on_a_control_motive_and_a_decision_note_otherwise():
    assert investigation_kind(verdict_payload()) == "ROOT CAUSE"
    assert investigation_kind(verdict_payload(motive="uncalibrated control")) == "ROOT CAUSE"
    assert investigation_kind(verdict_payload(motive="instrument error")) == "ROOT CAUSE"
    assert investigation_kind(verdict_payload("BLOCK", "content")) == "DECISION NOTE"
    assert investigation_kind(verdict_payload("PASS", "content")) == "DECISION NOTE"


def test_gates_to_investigate_picks_the_failing_ones_and_all_four_on_a_pass():
    assert gates_to_investigate(verdict_payload()) == ["rights"]
    v = verdict_payload()
    v["gates"][1]["seen_this_run"] = False
    v["gates"][2]["calibrated"] = False
    assert gates_to_investigate(v) == ["rights", "claim", "brand"]
    clean = verdict_payload("PASS", "content")
    clean["gates"][0].update({"status": "PASS", "reason": "ok"})
    assert gates_to_investigate(clean) == ["rights", "claim", "brand", "provenance"]


def fake_readonly_ctx(state: dict) -> SimpleNamespace:
    return SimpleNamespace(state=MappingProxyType(state), invocation_id=RUN)


def test_instruction_carries_the_run_the_logql_and_the_kind():
    text = investigator_instruction(fake_readonly_ctx({STATE_VERDICT: verdict_payload()}))
    assert f'{{app="airlock", gate="rights"}} |= "{RUN}"' in text  # braces survive: no {key} templating
    assert "nimbus-clean-clip" in text and "ROOT CAUSE" in text and "DECISION NOTE" not in text
    assert "rights" in text and "TimeoutError: fault injected" in text
    assert f"at most {INVESTIGATION_TOOL_BUDGET} calls" in text
    assert "alerting_manage_rules(operation=\"list\"" in text and "query_prometheus" in text and "grafanacloud-logs" in text


def test_instruction_on_a_pass_asks_for_a_decision_note():
    clean = verdict_payload("PASS", "content")
    clean["gates"][0].update({"status": "PASS", "reason": "ok"})
    clean["reasons"] = ["all 4 gates PASS, seen by Grafana, healthy and calibrated"]
    text = investigator_instruction(fake_readonly_ctx({STATE_VERDICT: clean}))
    assert "The verdict is PASS" in text and '"DECISION NOTE: "' in text and "ROOT CAUSE" not in text


def test_instruction_without_a_verdict_still_names_the_run():
    text = investigator_instruction(fake_readonly_ctx({}))
    assert RUN in text and "unknown-asset" in text


def test_compact_loki_answer_adds_time_utc_and_cuts_the_evidence():
    raw = loki_answer({"run_id": RUN, "gate": "rights", "status": "ERROR", "reasons": ["TimeoutError"]}, with_evidence=True)
    out = json.loads(compact_loki_answer(raw))
    row = out["data"][0]
    assert row["time_utc"] == "2026-09-05T00:08:33.325Z"
    body = json.loads(row["line"])
    assert "evidence" not in body and body["evidence_head"].endswith("...") and len(body["evidence_head"]) < 220
    assert body["reasons"] == ["TimeoutError"] and body["run_id"] == RUN
    assert compact_loki_answer("Loki query failed: (status 503)") == "Loki query failed: (status 503)"


def test_loki_lines_from_answer_and_their_formatting():
    raw = compact_loki_answer(loki_answer({"run_id": RUN, "gate": "rights", "status": "ERROR", "asset_id": "a", "reasons": ["TimeoutError: injected"], "fault": "timeout"},
                                          {"run_id": "e-old", "gate": "rights", "status": "PASS", "asset_id": "a", "reasons": ["cleared"]}))
    lines = loki_lines_from_answer(raw)
    assert [x["run_id"] for x in lines] == [RUN, "e-old"]
    assert lines[0]["fault"] == "timeout" and lines[0]["time_utc"] == "2026-09-05T00:08:33.325Z"
    assert format_loki_line(lines[0]) == f"2026-09-05T00:08:33.325Z rights ERROR (fault: timeout): TimeoutError: injected [run {RUN}]"
    assert loki_lines_from_answer("not json") == []


def test_note_kind_line_and_cited_lines():
    note = "The rights gate raised at 2026-09-05T00:08:33.325Z, an injected fault.\n**ROOT CAUSE:** injected timeout on rights."
    assert note_kind_line(note, "ROOT CAUSE") == "ROOT CAUSE:** injected timeout on rights."
    assert note_kind_line("no conclusion here", "ROOT CAUSE") is None
    lines = [{"time_utc": "2026-09-05T00:08:33.325Z", "gate": "rights", "run_id": "e-old"},
             {"time_utc": "2026-09-04T00:00:00.000Z", "gate": "rights", "run_id": RUN},
             {"time_utc": "2026-09-03T00:00:00.000Z", "gate": "claim", "run_id": "e-other"},
             {"time_utc": "2026-09-05T00:08:33.325Z", "gate": "rights", "run_id": "e-old"}]
    picked = cited_lines(note, lines, RUN)
    assert [(x["time_utc"], x["run_id"]) for x in picked] == [("2026-09-05T00:08:33.325Z", "e-old"), ("2026-09-04T00:00:00.000Z", RUN)]


def test_fallback_note_rests_on_the_verdict_and_says_why():
    note = fallback_note("ROOT CAUSE", verdict_payload(), "ConnectError: connection refused")
    assert note.startswith("investigation unavailable: ConnectError: connection refused")
    assert note_kind_line(note, "ROOT CAUSE").startswith("ROOT CAUSE: rights: control unavailable")
    assert "not investigated" in note


def test_budget_refuses_the_seventh_tool_call_and_closes_the_ninth_model_turn():
    budget = InvestigationBudget("ROOT CAUSE", tool_calls=6, model_calls=8, budget_s=1000)
    tool = SimpleNamespace(name="query_loki_logs")
    for _ in range(6):
        assert budget.before_tool(tool, {}, None) is None
    refusal = budget.before_tool(tool, {}, None)
    assert refusal == {"error": "tool budget of 6 calls spent: write the note now from the answers you have"}
    assert budget.stopped == "tool budget of 6 calls spent"
    for _ in range(8):
        assert budget.before_model(None, None) is None
    closing = budget.before_model(None, None)
    assert isinstance(closing, LlmResponse) and closing.content.parts[0].text.startswith("ROOT CAUSE: investigation stopped, tool budget of 6 calls spent")


def test_budget_keeps_the_alert_rule_tool_read_only():
    budget = InvestigationBudget("ROOT CAUSE")
    tool = SimpleNamespace(name="alerting_manage_rules")
    assert budget.before_tool(tool, {"operation": "list", "label_selectors": ['{app="airlock"}']}, None) is None
    assert budget.before_tool(tool, {"operation": "get", "rule_uid": "airlock-gate-errors"}, None) is None
    refused = budget.before_tool(tool, {"operation": "delete", "rule_uid": "airlock-gate-errors"}, None)
    assert refused == {"error": "alerting_manage_rules is read only here: operation 'delete' refused, use operation 'list'"}
    assert budget.before_tool(tool, {"operation": "update", "rule_uid": "x"}, None)["error"].startswith("alerting_manage_rules is read only")
    assert budget.stopped is None  # a refused write is not the end of the investigation


def test_budget_closes_the_loop_past_the_deadline_and_turns_errors_into_text():
    budget = InvestigationBudget("DECISION NOTE", budget_s=-1)
    closing = budget.before_model(None, None)
    assert isinstance(closing, LlmResponse) and "time budget" in closing.content.parts[0].text
    err = budget.on_tool_error(SimpleNamespace(name="query_prometheus"), {}, None, ValueError("bad expr"))
    assert err == {"error": "query_prometheus failed: ValueError: bad expr"}
    model_err = budget.on_model_error(None, None, RuntimeError("429 quota"))
    assert model_err.content.parts[0].text.startswith("investigation unavailable: model error: RuntimeError: 429 quota")


def test_after_tool_rewrites_loki_answers_only():
    budget = InvestigationBudget("ROOT CAUSE")
    raw = loki_answer({"run_id": RUN, "gate": "rights", "status": "PASS"}, with_evidence=True)
    changed = budget.after_tool(SimpleNamespace(name="query_loki_logs"), {}, None, {"content": [{"type": "text", "text": raw}], "isError": False})
    assert "time_utc" in changed["content"][0]["text"] and "evidence_head" in changed["content"][0]["text"]
    assert budget.after_tool(SimpleNamespace(name="query_prometheus"), {}, None, {"content": [{"type": "text", "text": raw}]}) is None


def fc_event(name: str, args: dict) -> Event:
    return Event(invocation_id=RUN, author="investigator", content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args, id="c1"))]))


def fr_event(name: str, response: dict) -> Event:
    return Event(invocation_id=RUN, author="investigator", content=types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(name=name, response=response, id="c1"))]))


def text_event(text: str, state_delta: dict | None = None) -> Event:
    from google.adk.events.event_actions import EventActions

    return Event(invocation_id=RUN, author="investigator", content=types.Content(role="model", parts=[types.Part(text=text)]), actions=EventActions(state_delta=state_delta or {}))


def test_tool_rows_read_function_calls_and_responses():
    raw = compact_loki_answer(loki_answer({"run_id": RUN, "gate": "rights", "status": "ERROR", "reasons": ["TimeoutError"]}))
    rows = tool_rows(fc_event("query_loki_logs", {"logql": "{app=\"airlock\"}"}))
    assert rows == [{"step": "tool_call", "tool": "query_loki_logs", "args": {"logql": "{app=\"airlock\"}"}}]
    rows = tool_rows(fr_event("query_loki_logs", {"content": [{"type": "text", "text": raw}], "isError": False}))
    assert rows[0]["step"] == "tool_result" and rows[0]["lines"] == 1 and rows[0]["loki_lines"][0]["run_id"] == RUN
    assert tool_rows(text_event("a note")) == []


def make_ctx(state: dict) -> InvocationContext:
    session = Session(id="s1", app_name="airlock", user_id="u1", state=state)
    return InvocationContext(session_service=InMemorySessionService(), invocation_id=RUN, agent=InvestigationAgent(name="investigation"), session=session)


def run_investigation(monkeypatch, state: dict, events: list[Event] | Exception) -> list[dict]:
    """Runs the wrapper with a fake investigator that yields the events (or raises) and a fake toolset."""
    closed = {"n": 0}

    class FakeToolset:
        async def close(self):
            closed["n"] += 1

    class FakeInvestigator:
        async def run_async(self, ctx):
            if isinstance(events, Exception):
                raise events
            for e in events:
                yield e

    monkeypatch.setattr(pipeline, "make_grafana_toolset", lambda tools: FakeToolset())
    monkeypatch.setattr(pipeline, "make_investigator", lambda budget, toolset: FakeInvestigator())

    async def collect():
        out = []
        async for ev in InvestigationAgent(name="investigation")._run_async_impl(make_ctx(state)):
            out.append(ev)
        return out

    out = asyncio.run(collect())
    assert closed["n"] == 1
    return out


def payloads_of(events: list[Event], author: str) -> list[dict]:
    out = []
    for ev in events:
        if ev.author != author or not ev.content or not ev.content.parts:
            continue
        for p in ev.content.parts:
            if p.text:
                try:
                    out.append(json.loads(p.text))
                except json.JSONDecodeError:
                    pass
    return out


def test_investigation_streams_tool_rows_and_stores_the_note(monkeypatch):
    raw = compact_loki_answer(loki_answer({"run_id": RUN, "gate": "rights", "status": "ERROR", "reasons": ["TimeoutError: injected"], "fault": "timeout"}))
    note = "The rights gate raised TimeoutError at 2026-09-05T00:08:33.325Z, an injected fault.\nROOT CAUSE: injected timeout on the rights gate."
    events = [fc_event("query_loki_logs", {"logql": "x"}), fr_event("query_loki_logs", {"content": [{"type": "text", "text": raw}]}),
              text_event(note, {INVESTIGATION_OUTPUT_KEY: note})]
    out = run_investigation(monkeypatch, {STATE_VERDICT: verdict_payload()}, events)
    # the LlmAgent's own events pass through, so the runner appends them and the model's next turn reads them
    assert [e.author for e in out] == ["investigation", "investigator", "investigation", "investigator", "investigator", "investigation"]
    rows = payloads_of(out, "investigation")
    assert rows[0]["step"] == "tool_call" and rows[1]["step"] == "tool_result" and rows[1]["lines"] == 1
    final = rows[-1]
    assert final["stage"] == "investigation" and final["kind"] == "ROOT CAUSE" and final["note"] == note
    assert final["tool_calls"] == 1 and final["conclusion"] == "ROOT CAUSE: injected timeout on the rights gate."
    assert final["cited"][0]["time_utc"] == "2026-09-05T00:08:33.325Z" and final["cited"][0]["fault"] == "timeout"
    assert "fallback" not in final
    assert out[-1].actions.state_delta[STATE_INVESTIGATION]["note"] == note
    assert out[-1].actions.state_delta[INVESTIGATION_OUTPUT_KEY] == note


def test_investigation_failure_becomes_a_fallback_note_and_the_run_continues(monkeypatch):
    out = run_investigation(monkeypatch, {STATE_VERDICT: verdict_payload()}, ConnectionError("connection refused"))
    final = payloads_of(out, "investigation")[-1]
    assert final["fallback"] is True and final["error"] == "ConnectionError: connection refused"
    assert final["note"].startswith("investigation unavailable: ConnectionError: connection refused")
    assert final["conclusion"].startswith("ROOT CAUSE: rights: control unavailable")


def test_investigation_with_no_text_falls_back_too(monkeypatch):
    out = run_investigation(monkeypatch, {STATE_VERDICT: verdict_payload("PASS", "content")}, [fc_event("alerting_manage_rules", {"operation": "list"}), fr_event("alerting_manage_rules", {"content": []})])
    final = payloads_of(out, "investigation")[-1]
    assert final["kind"] == "DECISION NOTE" and final["fallback"] is True and "the model returned no text" in final["note"]


def test_incident_owner_and_title():
    assert incident_owner(verdict_payload()) == "platform"
    paperwork = verdict_payload("BLOCK", "content", rule_ids=["16 CFR 255.3", "charter:tone"])
    assert incident_owner(paperwork) == "clearance"
    assert incident_owner(verdict_payload("BLOCK", "content", rule_ids=["charter:tone"])) == "platform"
    assert incident_title(verdict_payload(), "nimbus-clean-clip") == "Airlock needs a human: control unavailable on nimbus-clean-clip"


def test_find_open_incident_matches_the_title_and_takes_the_newest():
    listed = json.dumps({"incidents": [
        {"incidentId": "28", "title": "Airlock needs a human: control unavailable on nimbus-clean-clip", "status": "active", "createdTime": "2026-09-05T05:18:33Z"},
        {"incidentId": "29", "title": "Airlock needs a human: control unavailable on nimbus-clean-clip", "status": "active", "createdTime": "2026-09-05T05:20:14Z"},
        {"incidentId": "26", "title": "Airlock needs a human: content on nimbus-test-clip", "status": "active", "createdTime": "2026-09-05T03:30:12Z"},
        {"incidentId": "30", "title": "Airlock needs a human: control unavailable on nimbus-clean-clip", "status": "resolved", "createdTime": "2026-09-05T06:00:00Z"},
    ], "hasMore": False})
    hit = find_open_incident(listed, "Airlock needs a human: control unavailable on nimbus-clean-clip")
    assert hit["incidentId"] == "29"
    assert find_open_incident(listed, "Airlock needs a human: content on CrestToothpa-18-48") is None
    assert find_open_incident("not json", "x") is None


def test_incident_body_carries_the_routing_the_note_and_the_loki_lines():
    inv = {"note": "The rights gate raised.\nROOT CAUSE: injected timeout.", "tool_calls": 3, "model": "gemini-2.5-flash",
           "cited": [{"time_utc": "2026-09-05T00:08:33.325Z", "gate": "rights", "status": "ERROR", "reason": "TimeoutError", "run_id": RUN, "fault": "timeout"}]}
    body = incident_body(verdict_payload(), inv, "platform")
    assert body.startswith("Route to the platform owner")
    assert f"Run {RUN} on nimbus-clean-clip: BLOCK (control unavailable)." in body
    assert "Investigation (gemini-2.5-flash, 3 tool calls):" in body and "ROOT CAUSE: injected timeout." in body
    assert "- 2026-09-05T00:08:33.325Z rights ERROR (fault: timeout): TimeoutError [run e-7f3a]" in body
    assert "Reasons:\n- rights: control unavailable" in body
    clearance = incident_body(verdict_payload("BLOCK", "content", rule_ids=["16 CFR 255.3"]), {"note": "n", "tool_calls": 0}, "clearance")
    assert clearance.startswith("Route to the clearance owner (legal or agency): a licence, a release or a study lifts this block.")


def test_verdict_sample_no_longer_carries_incidents_total(monkeypatch):
    pushed = []

    class FakePusher:
        def push_lines(self, lines):
            pushed.extend(lines)
            return 204

    monkeypatch.setenv("GRAFANA_INFLUX_URL", "http://influx")
    monkeypatch.setattr(pipeline.InfluxPusher, "from_env", classmethod(lambda cls: FakePusher()))
    pipeline.push_verdict_sample("BLOCK", "control unavailable", True, 0.1)
    assert len(pushed) == 1 and "incidents_total" not in pushed[0] and "airlock_verdict,motive=control_unavailable,status=BLOCK" in pushed[0]
    pipeline.push_incident_sample("BLOCK", "control unavailable", "platform", attached=True)
    assert any(l.startswith("airlock_incident,motive=control_unavailable,owner=platform attached=1i,total=1i") for l in pushed)
    assert any(l.startswith("airlock_verdict,motive=control_unavailable,status=BLOCK incidents_total=1i") for l in pushed)


@pytest.mark.parametrize("motive", ["control unavailable", "content"])
def test_root_agent_runs_the_investigation_between_verdict_and_escalation(motive):
    del motive
    assert [a.name for a in pipeline.root_agent.sub_agents] == ["gates", "verdict", "investigation", "escalation"]
