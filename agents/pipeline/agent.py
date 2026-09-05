"""Airlock: the ADK pipeline. Four gate agents in parallel, then the verdict agent.

    root_agent = SequentialAgent(airlock)
        ParallelAgent(gates): rights, claim, brand, provenance   (each a BaseAgent around a plain gate function)
        VerdictAgent: asks Grafana five questions per gate through mcp-grafana (this run's event in
                      Loki, then four PromQL questions), applies the deterministic rules of
                      airlock.verdict, writes the annotation.
        EscalationAgent: opens a Grafana incident when the verdict says a human is needed.

ADK is the envelope. Every decision is plain Python under tests (airlock/gates/*, airlock/verdict.py).
The input message is a GCS URI, or a JSON object {"gcs_uri": ..., "asset_id": ...}, optionally with
"mute": ["rights"] (the gate runs but pushes nothing to Grafana) or "fault": {"rights": "timeout"}
(the gate fails before it spends anything). The run id is the ADK invocation id: every gate event
carries it, and the verdict asks Loki for THIS run's events, so a muted gate is dark by construction.
Inputs and gate results live under temp: state keys, scoped to the invocation, so a second message
in the same session is a new run.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Awaitable, Callable

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
from airlock.grafana_mcp import make_grafana_toolset, pick_datasource_uid, pinned_loki_uid, pinned_prometheus_uid, tool_text
from airlock.telemetry import InfluxPusher, line
from airlock.verdict import RUN_EVENT_WINDOW_MIN, GateHealth, Verdict, decide, logql_question, promql_questions

CHECKS = {
    "rights": (rights.check, rights.SOURCE_OF_TRUTH),
    "claim": (claim.check, claim.SOURCE_OF_TRUTH),
    "brand": (brand.check, brand.SOURCE_OF_TRUTH),
    "provenance": (provenance.check, provenance.SOURCE_OF_TRUTH),
}
# temp: keys are invocation-scoped in ADK (applied in memory, never persisted), so a session that
# receives a second message starts from the message, not from the first run's asset and mute list.
STATE_ASSET = "temp:airlock:asset"
STATE_GATE = "temp:airlock:gate:{}"
STATE_VERDICT = "temp:airlock:verdict"

# Grafana Cloud's free stack pauses after idle days and answers 503 "Loading" for about two minutes
# while it wakes (measured on the scheduled proof of 2026-09-04 and 2026-09-05, docs/RUNS.md); the
# verdict waits for it instead of failing the run.
WAKE_RETRY_S = 10
WAKE_BUDGET_S = 180
WAKE_MARKERS = ("status 503", "http 503", "503 service", '"code":"loading"', '"code": "loading"', "instance is loading", "connection refused")
# Loki ingestion lags the push by a few seconds, and the rights gate pushes right before the verdict asks.
LOKI_RETRY_S = 3
LOKI_RETRIES = 3


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


def _input_object(ctx: InvocationContext) -> dict[str, Any]:
    """The message as a JSON object when it is one, else {} (a bare URI or path carries no options)."""
    text = _user_text(ctx).strip()
    if text.startswith("{"):
        try:
            d = json.loads(text)
            return d if isinstance(d, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _asset_from_ctx(ctx: InvocationContext) -> Asset:
    """The asset of THIS run: the message first, then this invocation's temp state (same run id only).
    The run id is the invocation id, so every gate event of the run can be found again in Loki."""
    stored = ctx.session.state.get(STATE_ASSET)
    if stored and stored.get("run_id") == ctx.invocation_id:
        return Asset(**stored)
    asset = from_message(_user_text(ctx))
    asset.run_id = ctx.invocation_id
    return asset


def muted_gates(input_object: dict[str, Any]) -> list[str]:
    """The input may carry {"mute": ["rights"]}: those gates run but push nothing to Grafana, so the
    verdict has to notice through Grafana that the control went dark. A demo of R1, and a judge's action."""
    return [str(g) for g in (input_object.get("mute") or [])]


def injected_faults(input_object: dict[str, Any]) -> dict[str, str]:
    """The input may carry {"fault": {"rights": "timeout"}}: the gate raises before it spends anything,
    the ERROR lands in Loki and in the errors counter like a real one, and the verdict must notice."""
    faults = input_object.get("fault") or {}
    if not isinstance(faults, dict):
        return {}
    return {str(g): str(kind) for g, kind in faults.items() if kind}


class GateAgent(BaseAgent):
    """Runs one gate function with the telemetry envelope and stores the result in the invocation's state."""

    gate: str

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        asset = _asset_from_ctx(ctx)
        options = _input_object(ctx)
        muted = self.gate in muted_gates(options)
        fault = injected_faults(options).get(self.gate)
        fn, source = CHECKS[self.gate]
        running: dict[str, Any] = {"gate": self.gate, "stage": "running", "asset_id": asset.asset_id, "run_id": asset.run_id,
                                   "source_of_truth": source, "telemetry_muted": muted}
        if fault:
            running["fault"] = fault
        yield _text_event(ctx, self.name, json.dumps(running))
        # The gate functions block (Video Intelligence, Gemini, c2pa); a thread keeps the four gates parallel.
        result = await asyncio.to_thread(run_gate, self.gate, fn, asset, source, muted, fault)
        payload = result.to_dict()
        payload["telemetry_muted"] = muted
        payload["run_id"] = asset.run_id
        if fault:
            payload["fault"] = fault
        yield _text_event(ctx, self.name, json.dumps({"gate": self.gate, "stage": "done", **payload}, default=str),
                          state_delta={STATE_GATE.format(self.gate): payload, STATE_ASSET: asset.__dict__})


def run_cost(gate_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The cost of the run at list price: the sum of what each gate reported (pricing.yaml)."""
    total = 0.0
    per_gate: dict[str, float] = {}
    tokens_in = tokens_out = 0
    minutes = 0.0
    for gate, r in gate_results.items():
        u = (r or {}).get("usage") or {}
        if u.get("cost_usd") is None:
            continue
        per_gate[gate] = float(u["cost_usd"])
        total += float(u["cost_usd"])
        tokens_in += int(u.get("tokens_in") or 0)
        tokens_out += int(u.get("tokens_out") or 0)
        minutes += float(u.get("video_minutes") or 0)
    if not per_gate:  # no gate could price itself: say so, never show a free check
        errors = {g: (r or {}).get("usage", {}).get("error") for g, r in gate_results.items() if (r or {}).get("usage", {}).get("error")}
        return {"cost_usd": None, "per_gate": {}, "tokens_in": 0, "tokens_out": 0, "video_minutes": 0.0,
                "basis": "not measured" + (f": {json.dumps(errors)[:300]}" if errors else "")}
    return {"cost_usd": round(total, 6), "per_gate": per_gate, "tokens_in": tokens_in, "tokens_out": tokens_out, "video_minutes": minutes,
            "basis": "list prices of 2026-08-29 (pricing.yaml), free quotas not netted"}


def push_verdict_sample(status: str, motive: str, needs_human: bool, cost_usd: float | None = None) -> None:
    """One airlock_verdict sample per verdict, through the Influx endpoint (independent of the Grafana
    API, so the verdict agent's own failure leaves a trace too)."""
    if not os.environ.get("GRAFANA_INFLUX_URL"):
        return
    fields: dict[str, int | float] = {"total": 1, "needs_human": 1 if needs_human else 0, "incidents_total": 0}
    if cost_usd is not None:
        fields["cost_usd"] = float(cost_usd)
    InfluxPusher.from_env().push_lines([line("airlock_verdict", {"status": status, "motive": motive.replace(" ", "_")}, fields)])


def push_verdict_counters(verdict: Verdict, incident_opened: bool, cost_usd: float | None = None) -> None:
    """One sample per verdict so the console's stat tiles and the dashboard count real runs."""
    del incident_opened  # the escalation agent pushes airlock_incident when it opens one
    push_verdict_sample(verdict.status, verdict.motive, verdict.needs_human, cost_usd)


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


def parse_run_event(text: str, run_id: str) -> dict[str, Any] | None:
    """The newest log line of a query_loki_logs answer whose JSON body carries this run id, parsed;
    None when the answer holds no such line (or is not JSON at all)."""
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        return None
    rows = d.get("data") if isinstance(d, dict) else d
    if not isinstance(rows, list):
        return None
    for row in rows:  # newest first: the tool's default direction is backward
        raw_line = row.get("line") if isinstance(row, dict) else row
        if not isinstance(raw_line, str):
            continue
        try:
            body = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(body, dict) and body.get("run_id") == run_id:
            body.setdefault("status", (row.get("labels") or {}).get("status") if isinstance(row, dict) else None)
            body["_timestamp"] = loki_timestamp(row.get("timestamp") if isinstance(row, dict) else None)
            return body
    return None


def loki_timestamp(raw: Any) -> str | None:
    """mcp-grafana returns the line's nanosecond timestamp as a quoted string ("\"1788566913325404907\""); read it as UTC."""
    if raw is None:
        return None
    digits = str(raw).strip().strip('"')
    if not digits.isdigit():
        return str(raw)
    return datetime.fromtimestamp(int(digits) / 1e9, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def looks_like_waking(text: str) -> bool:
    """A Grafana Cloud stack that is paused answers 503 "Loading" (or refuses the connection) while it wakes."""
    low = text.lower()
    return any(marker in low for marker in WAKE_MARKERS)


class GrafanaWaiter:
    """Retries an MCP call while Grafana Cloud is starting, every WAKE_RETRY_S for up to WAKE_BUDGET_S,
    and remembers how long it waited so the verdict can say so."""

    def __init__(self, retry_s: float = WAKE_RETRY_S, budget_s: float = WAKE_BUDGET_S, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self.retry_s = retry_s
        self.budget_s = budget_s
        self.sleep = sleep
        self.waited_s = 0.0
        self.attempts = 0

    async def call(self, tool_call: Callable[[], Awaitable[Any]]) -> str:
        deadline = time.monotonic() + self.budget_s
        while True:
            self.attempts += 1
            try:
                text = tool_text(await tool_call())
                if not looks_like_waking(text):
                    return text
                last = text
            except Exception as exc:
                if not looks_like_waking(f"{type(exc).__name__}: {exc}"):
                    raise
                last = f"{type(exc).__name__}: {exc}"
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Grafana Cloud still starting after {int(self.waited_s)} s: {last[:300]}")
            await self.sleep(self.retry_s)
            self.waited_s += self.retry_s


class VerdictAgent(BaseAgent):
    """Asks Grafana about each gate (this run's event in Loki, then PromQL), decides, writes the annotation."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        asset = _asset_from_ctx(ctx)
        run_id = asset.run_id or ctx.invocation_id
        gate_results = {g: ctx.session.state.get(STATE_GATE.format(g)) or {"status": "ERROR", "reasons": ["gate did not report"], "rule_ids": []} for g in GATES}
        toolset = make_grafana_toolset(["list_datasources", "query_prometheus", "query_loki_logs", "create_annotation"])
        tool_ctx = Context(invocation_context=ctx)
        waiter = GrafanaWaiter()
        started = time.time()
        try:
            tools = {t.name: t for t in await toolset.get_tools(tool_ctx)}

            async def ask(name: str, args: dict[str, Any]) -> str:
                return await waiter.call(lambda: tools[name].run_async(args=args, tool_context=tool_ctx))

            prom_uid, loki_uid = pinned_prometheus_uid(), pinned_loki_uid()
            if not prom_uid:  # an empty pin means "ask"; the default pin skips the round trip and the guess
                prom_uid = pick_datasource_uid(await ask("list_datasources", {"type": "prometheus"}), "prometheus")
            if not loki_uid:
                loki_uid = pick_datasource_uid(await ask("list_datasources", {"type": "loki"}), "loki")

            # Question 1, Loki: this run's event of each gate. Asked for every gate first, then again for
            # the gates still unseen, so the ingestion wait is shared and bounded.
            end = datetime.now(timezone.utc) + timedelta(minutes=1)
            start = end - timedelta(minutes=RUN_EVENT_WINDOW_MIN + 1)
            seen: dict[str, dict[str, Any] | None] = {}
            logql = {g: logql_question(g, run_id) for g in GATES}
            for attempt in range(1 + LOKI_RETRIES):
                if attempt:
                    await asyncio.sleep(LOKI_RETRY_S)
                for gate in GATES:
                    if seen.get(gate):
                        continue
                    raw = await ask("query_loki_logs", {"datasourceUid": loki_uid, "logql": logql[gate], "limit": 20,
                                                        "startRfc3339": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "endRfc3339": end.strftime("%Y-%m-%dT%H:%M:%SZ")})
                    seen[gate] = parse_run_event(raw, run_id)
                if all(seen.get(g) for g in GATES):
                    break
            if waiter.waited_s > 0:
                yield _text_event(ctx, self.name, json.dumps({"stage": "grafana", "note": f"Grafana Cloud was starting, waited {int(waiter.waited_s)} s"}))

            # Questions 2 to 5, PromQL, per gate.
            health: dict[str, GateHealth] = {}
            for gate in GATES:
                event = seen.get(gate)
                answers: dict[str, Any] = {"seen_this_run": {"expr": logql[gate], "value": 1.0 if event else 0.0,
                                                             "event_status": event.get("status") if event else None,
                                                             "event_timestamp": event.get("_timestamp") if event else None}}
                for key, expr in promql_questions(gate).items():
                    raw = await ask("query_prometheus", {"datasourceUid": prom_uid, "expr": expr, "queryType": "instant", "endTime": "now"})
                    answers[key] = {"expr": expr, "value": parse_instant_value(raw)}
                health[gate] = GateHealth(gate, answers["error_rate_15m"]["value"], answers["seconds_since_success"]["value"],
                                          answers["calibration_catches_7d"]["value"], answers["last_calibration_caught"]["value"],
                                          seen_this_run=bool(event), runs_15m=answers["runs_15m"]["value"], raw=answers)
                yield _text_event(ctx, self.name, json.dumps({"stage": "grafana", "gate": gate, "run_id": run_id, "answers": answers, "health": health[gate].describe(),
                                                              "seen_this_run": bool(event), "calibrated": health[gate].calibrated,
                                                              "calibration": health[gate].calibration_note()}))
            verdict = decide(gate_results, health)
            payload = verdict.to_dict()
            payload["asset_id"] = asset.asset_id
            payload["run_id"] = run_id
            if waiter.waited_s > 0:
                payload["note"] = f"Grafana Cloud was starting, waited {int(waiter.waited_s)} s"
            tags = ["airlock", "verdict", verdict.status.lower(), asset.asset_id[:40], os.environ.get("AIRLOCK_RUNTIME", "local")]
            ann = await ask("create_annotation", {
                "dashboardUid": os.environ.get("AIRLOCK_DASHBOARD_UID", "airlock-gates"),
                "time": int(time.time() * 1000),
                "text": f"{verdict.status} ({verdict.motive}) {asset.asset_id} run {run_id}: " + " | ".join(verdict.reasons)[:900],
                "tags": tags})
            try:
                payload["annotation_id"] = json.loads(ann).get("Payload", {}).get("id")
            except (json.JSONDecodeError, AttributeError):
                payload["annotation_raw"] = ann[:300]
            payload["elapsed_ms"] = int((time.time() - started) * 1000)
            payload["cost"] = run_cost(gate_results)
            try:
                push_verdict_counters(verdict, False, payload["cost"].get("cost_usd"))
            except Exception as exc:  # telemetry must not hide a verdict, but its failure is said
                payload["telemetry_error"] = f"{type(exc).__name__}: {exc}"
            yield _text_event(ctx, self.name, json.dumps({"stage": "verdict", **payload}, default=str), state_delta={STATE_VERDICT: payload})
        except Exception as exc:
            failure: dict[str, Any] = {"stage": "verdict", "status": "ERROR", "motive": "instrument error", "needs_human": True, "run_id": run_id,
                                       "reasons": [f"verdict agent could not complete: {type(exc).__name__}: {exc}"]}
            if waiter.waited_s > 0:
                failure["note"] = f"Grafana Cloud was starting, waited {int(waiter.waited_s)} s"
            try:  # the trace of the failure goes through Influx, which does not depend on the Grafana API
                push_verdict_sample("ERROR", "instrument error", True)
            except Exception as push_exc:
                failure["telemetry_error"] = f"{type(push_exc).__name__}: {push_exc}"
            yield _text_event(ctx, self.name, json.dumps(failure, default=str))
            raise
        finally:
            await toolset.close()


class EscalationAgent(BaseAgent):
    """On a BLOCK only a human can arbitrate (a control unavailable, uncalibrated or in error), opens a
    Grafana incident and says so. A content BLOCK needs no human: the rule already decided."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        verdict = ctx.session.state.get(STATE_VERDICT) or {}
        asset_id = verdict.get("asset_id", "unknown-asset")
        if not verdict.get("needs_human"):
            yield _text_event(ctx, self.name, json.dumps({"stage": "escalation", "opened": False,
                                                          "reason": f"no human needed: verdict {verdict.get('status', '?')} on {verdict.get('motive', '?')}"}))
            return
        toolset = make_grafana_toolset(["create_incident", "create_annotation"])
        tool_ctx = Context(invocation_context=ctx)
        started = time.time()
        try:
            tools = {t.name: t for t in await toolset.get_tools(tool_ctx)}
            reasons = verdict.get("reasons", [])
            inc = tool_text(await tools["create_incident"].run_async(args={
                "title": f"Airlock needs a human: {verdict.get('motive')} on {asset_id}"[:120],
                "severity": "minor",
                "roomPrefix": "airlock",
                "status": "active",
                "isDrill": os.environ.get("AIRLOCK_INCIDENT_DRILL", "true") == "true",
                "labels": [{"key": "airlock", "label": str(verdict.get("motive", "")).replace(" ", "-")}],
                "attachCaption": "Reasons: " + " | ".join(reasons)[:400]}, tool_context=tool_ctx))
            payload: dict[str, Any] = {"stage": "escalation", "opened": True, "incident_raw": inc[:500], "elapsed_ms": int((time.time() - started) * 1000)}
            try:
                d = json.loads(inc)
                incident = d.get("incident") or d
                payload["incident_id"] = incident.get("incidentID") or incident.get("id")
                payload["incident_url"] = incident.get("incidentURL") or incident.get("url")
                payload["incident_title"] = incident.get("title")
            except (json.JSONDecodeError, AttributeError):
                pass
            if not payload.get("incident_id"):
                # The plan's fallback: the Incident API refused (a free stack whose Incident app was never
                # opened answers a foreign-key error). A second annotation tagged needs-human carries the
                # hand-off instead, and the console shows the approval button. Said here, not hidden.
                payload["opened"] = False
                payload["fallback"] = "needs-human annotation"
                ann = tool_text(await tools["create_annotation"].run_async(args={
                    "dashboardUid": os.environ.get("AIRLOCK_DASHBOARD_UID", "airlock-gates"),
                    "time": int(time.time() * 1000),
                    "text": f"NEEDS HUMAN ({verdict.get('motive')}) {asset_id}: " + " | ".join(reasons)[:800],
                    "tags": ["airlock", "needs-human", asset_id[:40], os.environ.get("AIRLOCK_RUNTIME", "local")]}, tool_context=tool_ctx))
                try:
                    payload["fallback_annotation_id"] = json.loads(ann).get("Payload", {}).get("id")
                except (json.JSONDecodeError, AttributeError):
                    payload["fallback_annotation_raw"] = ann[:300]
            if os.environ.get("GRAFANA_INFLUX_URL"):
                try:
                    InfluxPusher.from_env().push_lines([line("airlock_incident", {"motive": str(verdict.get("motive", "")).replace(" ", "_")}, {"total": 1})])
                except Exception as exc:
                    payload["telemetry_error"] = f"{type(exc).__name__}: {exc}"
            yield _text_event(ctx, self.name, json.dumps(payload, default=str), state_delta={"temp:airlock:escalation": payload})
        except Exception as exc:
            yield _text_event(ctx, self.name, json.dumps({"stage": "escalation", "opened": False, "error": f"{type(exc).__name__}: {exc}"}))
            raise
        finally:
            await toolset.close()


gate_agents = [GateAgent(name=f"{g}_gate", gate=g, description=f"{g} gate: {CHECKS[g][1]}") for g in GATES]
gates = ParallelAgent(name="gates", sub_agents=gate_agents, description="the four gates, in parallel")
verdict = VerdictAgent(name="verdict", description="asks Grafana about each gate, decides, writes the annotation")
escalation = EscalationAgent(name="escalation", description="opens a Grafana incident when only a human can arbitrate the BLOCK")
root_agent = SequentialAgent(name="airlock", sub_agents=[gates, verdict, escalation], description="Airlock: ship or block a generated asset on proof")
