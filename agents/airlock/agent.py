"""Airlock: the ADK pipeline. Four gate agents in parallel, then the verdict agent.

    root_agent = SequentialAgent(airlock)
        ParallelAgent(gates): rights, claim, brand, provenance   (each a BaseAgent around a plain gate function)
        VerdictAgent: asks Grafana three PromQL questions per gate through mcp-grafana, applies the
                      deterministic rules of airlock.verdict, writes the annotation, opens an incident
                      when a human is needed.

ADK is the envelope. Every decision is plain Python under tests (airlock/gates/*, airlock/verdict.py).
The input message is a GCS URI, or a JSON object {"gcs_uri": ..., "asset_id": ...}.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.context import Context
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai import types

from airlock.assets import from_message
from airlock.gates import brand, claim, provenance, rights
from airlock.gates.base import GATES, Asset, run_gate
from airlock.grafana_mcp import make_grafana_toolset
from airlock.verdict import GateHealth, decide, promql_questions

CHECKS = {
    "rights": (rights.check, rights.SOURCE_OF_TRUTH),
    "claim": (claim.check, claim.SOURCE_OF_TRUTH),
    "brand": (brand.check, brand.SOURCE_OF_TRUTH),
    "provenance": (provenance.check, provenance.SOURCE_OF_TRUTH),
}
STATE_ASSET = "airlock:asset"
STATE_GATE = "airlock:gate:{}"
STATE_VERDICT = "airlock:verdict"


def _text_event(ctx: InvocationContext, author: str, text: str, state_delta: dict[str, Any] | None = None) -> Event:
    return Event(
        invocation_id=ctx.invocation_id,
        author=author,
        branch=ctx.branch,
        content=types.Content(role="model", parts=[types.Part(text=text)]),
        actions=EventActions(state_delta=state_delta or {}),
    )


def _user_text(ctx: InvocationContext) -> str:
    if ctx.user_content and ctx.user_content.parts:
        return "".join(p.text or "" for p in ctx.user_content.parts)
    return ""


def _asset_from_ctx(ctx: InvocationContext) -> Asset:
    stored = ctx.session.state.get(STATE_ASSET)
    if stored:
        return Asset(**stored)
    return from_message(_user_text(ctx))


class GateAgent(BaseAgent):
    """Runs one gate function with the telemetry envelope and stores the result in session state."""

    gate: str

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        asset = _asset_from_ctx(ctx)
        fn, source = CHECKS[self.gate]
        yield _text_event(ctx, self.name, json.dumps({"gate": self.gate, "stage": "running", "asset_id": asset.asset_id, "source_of_truth": source}))
        result = run_gate(self.gate, fn, asset, source)
        payload = result.to_dict()
        yield _text_event(ctx, self.name, json.dumps({"gate": self.gate, "stage": "done", **payload}, default=str),
                          state_delta={STATE_GATE.format(self.gate): payload, STATE_ASSET: asset.__dict__})


def tool_text(result: Any) -> str:
    if isinstance(result, dict):
        parts = result.get("content")
        if isinstance(parts, list):
            return "\n".join(str(p.get("text", p)) if isinstance(p, dict) else str(p) for p in parts)
        return json.dumps(result)
    return str(result)


def parse_instant_value(text: str) -> float | None:
    """The first sample value of a query_prometheus instant answer, or None when there is no sample."""
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        return None
    rows = d.get("data") if isinstance(d, dict) else d
    if not rows:
        return None
    v = rows[0].get("value") if isinstance(rows[0], dict) else None
    if not v or len(v) < 2:
        return None
    try:
        x = float(v[1])
    except (TypeError, ValueError):
        return None
    return None if x != x else x  # NaN means no sample


class VerdictAgent(BaseAgent):
    """Asks Grafana about each gate, decides, writes the annotation and the incident."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        asset = _asset_from_ctx(ctx)
        gate_results = {g: ctx.session.state.get(STATE_GATE.format(g)) or {"status": "ERROR", "reasons": ["gate did not report"], "rule_ids": []} for g in GATES}
        toolset = make_grafana_toolset(["list_datasources", "query_prometheus", "create_annotation", "create_incident"])
        tool_ctx = Context(invocation_context=ctx)
        started = time.time()
        try:
            tools = {t.name: t for t in await toolset.get_tools(tool_ctx)}
            ds_text = tool_text(await tools["list_datasources"].run_async(args={"type": "prometheus"}, tool_context=tool_ctx))
            prom_uid = next(d["uid"] for d in json.loads(ds_text) if d.get("type") == "prometheus")
            health: dict[str, GateHealth] = {}
            for gate in GATES:
                answers: dict[str, Any] = {}
                for key, expr in promql_questions(gate).items():
                    raw = tool_text(await tools["query_prometheus"].run_async(
                        args={"datasourceUid": prom_uid, "expr": expr, "queryType": "instant", "endTime": "now"}, tool_context=tool_ctx))
                    answers[key] = {"expr": expr, "value": parse_instant_value(raw)}
                health[gate] = GateHealth(gate, answers["error_rate_15m"]["value"], answers["seconds_since_success"]["value"],
                                          answers["calibration_catches_7d"]["value"], raw=answers)
                yield _text_event(ctx, self.name, json.dumps({"stage": "grafana", "gate": gate, "answers": answers, "health": health[gate].describe(), "calibrated": health[gate].calibrated}))
            verdict = decide(gate_results, health)
            payload = verdict.to_dict()
            payload["asset_id"] = asset.asset_id
            tags = ["airlock", "verdict", verdict.status.lower(), asset.asset_id[:40], os.environ.get("AIRLOCK_RUNTIME", "local")]
            ann = tool_text(await tools["create_annotation"].run_async(args={
                "dashboardUid": os.environ.get("AIRLOCK_DASHBOARD_UID", "airlock-gates"),
                "time": int(time.time() * 1000),
                "text": f"{verdict.status} ({verdict.motive}) {asset.asset_id}: " + " | ".join(verdict.reasons)[:900],
                "tags": tags}, tool_context=tool_ctx))
            try:
                payload["annotation_id"] = json.loads(ann).get("Payload", {}).get("id")
            except (json.JSONDecodeError, AttributeError):
                payload["annotation_raw"] = ann[:300]
            if verdict.needs_human:
                inc = tool_text(await tools["create_incident"].run_async(args={
                    "title": f"Airlock needs a human: {verdict.motive} on {asset.asset_id}"[:120],
                    "severity": "minor",
                    "roomPrefix": "airlock",
                    "status": "active",
                    "isDrill": os.environ.get("AIRLOCK_INCIDENT_DRILL", "true") == "true",
                    "labels": [{"key": "airlock", "label": verdict.motive.replace(" ", "-")}],
                    "attachCaption": "Reasons: " + " | ".join(verdict.reasons)[:400]}, tool_context=tool_ctx))
                payload["incident_raw"] = inc[:500]
                try:
                    d = json.loads(inc)
                    payload["incident_id"] = d.get("incidentID") or d.get("id") or (d.get("incident") or {}).get("incidentID")
                    payload["incident_url"] = (d.get("incident") or d).get("incidentURL") or d.get("url")
                except json.JSONDecodeError:
                    pass
            payload["elapsed_ms"] = int((time.time() - started) * 1000)
            yield _text_event(ctx, self.name, json.dumps({"stage": "verdict", **payload}, default=str), state_delta={STATE_VERDICT: payload})
        except Exception as exc:
            yield _text_event(ctx, self.name, json.dumps({"stage": "verdict", "status": "ERROR", "motive": "instrument error", "needs_human": True,
                                                          "reasons": [f"verdict agent could not complete: {type(exc).__name__}: {exc}"]}))
            raise
        finally:
            await toolset.close()


gate_agents = [GateAgent(name=f"{g}_gate", gate=g, description=f"{g} gate: {CHECKS[g][1]}") for g in GATES]
gates = ParallelAgent(name="gates", sub_agents=gate_agents, description="the four gates, in parallel")
verdict = VerdictAgent(name="verdict", description="asks Grafana about each gate, decides, writes the annotation and the incident")
root_agent = SequentialAgent(name="airlock", sub_agents=[gates, verdict], description="Airlock: ship or block a generated asset on proof")
