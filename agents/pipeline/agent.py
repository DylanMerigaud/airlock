"""Airlock: the ADK pipeline. Four gate agents in parallel, the verdict, the investigator, the escalation.

    root_agent = SequentialAgent(airlock)
        ParallelAgent(gates): rights, claim, brand, provenance   (each a BaseAgent around a plain gate function)
        VerdictAgent: asks Grafana five questions per gate through mcp-grafana (this run's event in
                      Loki, then four PromQL questions), applies the deterministic rules of
                      airlock.verdict, writes the annotation.
        InvestigationAgent: wraps the one LlmAgent of the pipeline (gemini-2.5-flash, the same
                      mcp-grafana toolset): it reads this run's Loki lines, the previous runs of the
                      failing gate, the counters and the alert rules, and writes a note of at most 60
                      words that names the cause (ROOT CAUSE on a control motive, DECISION NOTE on a
                      content verdict or a PASS). At most 6 tool calls; any failure becomes a fallback
                      note; the verdict never depends on it.
        EscalationAgent: when the verdict says a human is needed, opens a Grafana incident (label
                      owner:clearance for paperwork, owner:platform for a control) or attaches the run
                      to the open incident of the same asset and motive, with the note and the Loki
                      lines it cites.

ADK is the envelope. Every decision is plain Python under tests (airlock/gates/*, airlock/verdict.py);
the LlmAgent explains, it does not decide.
The input message is a GCS URI, or a JSON object {"gcs_uri": ..., "asset_id": ...}, optionally with
"mute": ["rights"] (the gate runs but pushes nothing to Grafana) or "fault": {"rights": "timeout"}
(the gate fails before it spends anything). The run id is the ADK invocation id: every gate event
carries it, and the verdict asks Loki for THIS run's events, so a muted gate is dark by construction.
Inputs and gate results live under temp: state keys, scoped to the invocation, so a second message
in the same session is a new run.
One trace per run in Tempo (airlock.tracing): ADK's spans around the agents and the investigator's
calls, one span per gate and per Grafana call of the verdict and the escalation; the trace id goes
into every Loki line, the gate and verdict payloads, the annotation and the incident.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.context import Context
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.genai import types

from airlock import settings, tracing
from airlock.assets import from_message
from airlock.gates import CHECKS, GATES
from airlock.gates.base import Asset, run_gate
from airlock.grafana_mcp import make_grafana_toolset, pick_datasource_uid, pinned_loki_uid, pinned_prometheus_uid, tool_text
from airlock.telemetry import line, shared_pushers
from airlock.verdict import RUN_EVENT_WINDOW_MIN, GateHealth, Verdict, decide, logql_question, needs_paperwork, promql_questions

# One trace per run in Tempo: ADK's spans (the invocation, one per agent, the investigator's tool and model
# calls) and Airlock's own (one per gate, one per Grafana call the verdict and the escalation make) leave
# through the OTLP exporter this installs, when GRAFANA_OTLP_TOKEN is set; the process that loads this module
# (adk api_server on Agent Engine, adk run locally) is the one that runs the pipeline.
tracing.configure()

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


def _text_event(ctx: InvocationContext, author: str, text: str, state_delta: dict[str, Any] | None = None, isolation_scope: str | None = None) -> Event:
    return Event(
        invocation_id=ctx.invocation_id,
        author=author,
        branch=ctx.branch,
        isolation_scope=isolation_scope,
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
        if trace_id := tracing.current_trace_id():
            payload["trace_id"] = trace_id
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
    API, so the verdict agent's own failure leaves a trace too). No incidents_total here: the verdict
    does not know yet; the escalation pushes that field when it opens or joins an incident."""
    influx, _ = shared_pushers()
    if influx is None:
        return
    fields: dict[str, int | float] = {"total": 1, "needs_human": 1 if needs_human else 0}
    if cost_usd is not None:
        fields["cost_usd"] = float(cost_usd)
    influx.push_lines([line("airlock_verdict", {"status": status, "motive": motive.replace(" ", "_")}, fields)])


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
    return datetime.fromtimestamp(int(digits) / 1e9, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


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


def annotation_text(verdict: Verdict, asset_id: str, run_id: str, trace_id: str | None) -> str:
    """The verdict annotation on the dashboard: status, motive, asset, run, the trace id when the run has one, the reasons."""
    head = f"{verdict.status} ({verdict.motive}) {asset_id} run {run_id}" + (f" trace {trace_id}" if trace_id else "")
    return f"{head}: " + " | ".join(verdict.reasons)[:900]


def trace_fields(trace_id: str | None) -> dict[str, str]:
    """trace_id and trace_url for a payload, empty when the process has no trace."""
    return {"trace_id": trace_id, "trace_url": tracing.explore_url(trace_id)} if trace_id else {}


class VerdictAgent(BaseAgent):
    """Asks Grafana about each gate (this run's event in Loki, then PromQL), decides, writes the annotation."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        asset = _asset_from_ctx(ctx)
        run_id = asset.run_id or ctx.invocation_id
        trace_id = tracing.current_trace_id()
        gate_results = {g: ctx.session.state.get(STATE_GATE.format(g)) or {"status": "ERROR", "reasons": ["gate did not report"], "rule_ids": []}
                        for g in GATES}
        toolset = make_grafana_toolset(["list_datasources", "query_prometheus", "query_loki_logs", "create_annotation"])
        tool_ctx = Context(invocation_context=ctx)
        waiter = GrafanaWaiter()
        started = time.time()
        try:
            tools = {t.name: t for t in await toolset.get_tools(tool_ctx)}

            async def ask(name: str, args: dict[str, Any]) -> str:
                # No ADK span wraps a tool the agent calls itself: one grafana.<tool> span per question, in the run's trace.
                with tracing.span(f"grafana.{name}", tool=name, run_id=run_id):
                    return await waiter.call(lambda: tools[name].run_async(args=args, tool_context=tool_ctx))

            prom_uid, loki_uid = pinned_prometheus_uid(), pinned_loki_uid()
            if not prom_uid:  # an empty pin means "ask"; the default pin skips the round trip and the guess
                prom_uid = pick_datasource_uid(await ask("list_datasources", {"type": "prometheus"}), "prometheus")
            if not loki_uid:
                loki_uid = pick_datasource_uid(await ask("list_datasources", {"type": "loki"}), "loki")

            # Question 1, Loki: this run's event of each gate. Asked for every gate first, then again for
            # the gates still unseen, so the ingestion wait is shared and bounded. A muted gate pushes
            # nothing on purpose: it is asked once, so R1 still rests on Grafana's own view and not an
            # assumption, but never retried (found live, 2026-09-05: 9 s of retries spent confirming
            # silence the mute switch already guaranteed).
            end = datetime.now(UTC) + timedelta(minutes=1)
            start = end - timedelta(minutes=RUN_EVENT_WINDOW_MIN + 1)
            muted = set(muted_gates(_input_object(ctx)))
            seen: dict[str, dict[str, Any] | None] = {}
            settled: set[str] = set()
            logql = {g: logql_question(g, run_id) for g in GATES}
            for attempt in range(1 + LOKI_RETRIES):
                if attempt:
                    await asyncio.sleep(LOKI_RETRY_S)
                for gate in GATES:
                    if seen.get(gate) or gate in settled:
                        continue
                    raw = await ask("query_loki_logs", {"datasourceUid": loki_uid, "logql": logql[gate], "limit": 20,
                                                        "startRfc3339": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "endRfc3339": end.strftime("%Y-%m-%dT%H:%M:%SZ")})
                    seen[gate] = parse_run_event(raw, run_id)
                    if seen[gate] is None and gate in muted:
                        settled.add(gate)
                if all(seen.get(g) or g in settled for g in GATES):
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
                yield _text_event(ctx, self.name, json.dumps({"stage": "grafana", "gate": gate, "run_id": run_id, "answers": answers,
                                                              "health": health[gate].describe(),
                                                              "seen_this_run": bool(event), "calibrated": health[gate].calibrated,
                                                              "unavailable": health[gate].unavailable,
                                                              "calibration": health[gate].calibration_note()}))
            verdict = decide(gate_results, health)
            payload = verdict.to_dict()
            payload["asset_id"] = asset.asset_id
            payload["run_id"] = run_id
            # The uids this run actually resolved (a pin, or a live list_datasources answer): the
            # investigator reads this run's own resolution instead of hardcoding a fallback that could
            # name a datasource absent on another judge's stack (found by the third panel, 2026-09-05).
            payload["datasources"] = {"loki_uid": loki_uid, "prom_uid": prom_uid}
            payload.update(trace_fields(trace_id))
            if waiter.waited_s > 0:
                payload["note"] = f"Grafana Cloud was starting, waited {int(waiter.waited_s)} s"
            tags = ["airlock", "verdict", verdict.status.lower(), asset.asset_id[:40], settings.runtime()]
            ann = await ask("create_annotation", {
                "dashboardUid": settings.dashboard_uid(),
                "time": int(time.time() * 1000),
                "text": annotation_text(verdict, asset.asset_id, run_id, trace_id),
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
                                       "reasons": [f"verdict agent could not complete: {type(exc).__name__}: {exc}"], **trace_fields(trace_id)}
            if waiter.waited_s > 0:
                failure["note"] = f"Grafana Cloud was starting, waited {int(waiter.waited_s)} s"
            try:  # the trace of the failure goes through Influx, which does not depend on the Grafana API
                push_verdict_sample("ERROR", "instrument error", True)
            except Exception as push_exc:
                failure["telemetry_error"] = f"{type(push_exc).__name__}: {push_exc}"
            # The failure is the verdict of this run (ERROR, instrument error, a human's): it goes into state so
            # the investigator and the escalation still run on it; when Grafana is back they write the
            # needs-human record, when it is not they say so in their own payloads. The run is never lost to
            # an exception a downstream agent could have explained.
            failure["gates"] = [{"gate": g, "status": (gate_results.get(g) or {}).get("status"),
                                 "reason": ((gate_results.get(g) or {}).get("reasons") or [""])[0],
                                 "seen_this_run": None, "calibrated": None, "calibration": "unknown, the verdict could not ask"} for g in GATES]
            failure["asset_id"] = asset.asset_id
            failure["elapsed_ms"] = int((time.time() - started) * 1000)
            yield _text_event(ctx, self.name, json.dumps(failure, default=str), state_delta={STATE_VERDICT: failure})
        finally:
            await toolset.close()



# The investigator: the one LLM agent of the pipeline. It reads what Grafana holds about this run
# (this run's Loki lines, the previous runs of the failing gate, the counters, the alert rules)
# through the same mcp-grafana toolset and writes a short note naming the cause. The verdict never
# depends on it: it explains the verdict, it does not make it. Bounded: at most
# INVESTIGATION_TOOL_BUDGET tool calls, INVESTIGATION_MODEL_CALLS model turns and
# INVESTIGATION_BUDGET_S of wall time, and any failure becomes a deterministic fallback note.
INVESTIGATOR_MODEL = "gemini-2.5-flash"
# mcp-grafana 1.3.0 names its alert rule tool alerting_manage_rules (operations list, get, versions, create,
# update, delete); the budget refuses anything but the read operations.
INVESTIGATION_TOOLS = ["query_loki_logs", "query_prometheus", "alerting_manage_rules"]
ALERT_RULE_READ_OPERATIONS = ("list", "get")
INVESTIGATION_TOOL_BUDGET = 6
INVESTIGATION_MODEL_CALLS = 8
INVESTIGATION_BUDGET_S = 150
INVESTIGATION_NOTE_WORDS = 60
INVESTIGATION_THINKING_TOKENS = 1024  # gemini-2.5-flash thinks before it calls a tool; the thoughts count against max_output_tokens
INVESTIGATION_OUTPUT_TOKENS = 4096
INVESTIGATION_OUTPUT_KEY = "airlock:investigation"  # the LlmAgent's output_key: the note as text
STATE_INVESTIGATION = "temp:airlock:investigation"  # the wrapper's payload: note, tool calls, Loki lines
# The rows the wrapper streams between the LlmAgent's own events (one per tool call and answer) carry an
# isolation scope of their own, so ADK keeps them out of the model's context: an event by another author in
# the middle of a tool turn would otherwise anchor the model's next turn after its own function call, and the
# function responses would be dropped as orphans (measured on 2026-09-05 with the first build).
INVESTIGATION_ROW_SCOPE = "airlock:investigation-rows"
CONTROL_MOTIVES = ("control unavailable", "uncalibrated control", "instrument error")
EVIDENCE_HEAD_CHARS = 200
LOKI_LINES_KEPT = 8


def investigation_kind(verdict: dict[str, Any]) -> str:
    """ROOT CAUSE when the verdict rests on the state of a control, DECISION NOTE for a content BLOCK or a PASS."""
    return "ROOT CAUSE" if verdict.get("motive") in CONTROL_MOTIVES else "DECISION NOTE"


def gates_to_investigate(verdict: dict[str, Any]) -> list[str]:
    """The gates the note should rest on: the ones in error, blocking, unseen or uncalibrated; on a PASS, all four."""
    lines = verdict.get("gates") or []
    picked = [g["gate"] for g in lines if g.get("status") != "PASS" or g.get("seen_this_run") is False or g.get("calibrated") is False]
    return picked or [g["gate"] for g in lines] or list(GATES)


def investigator_instruction(ctx: ReadonlyContext) -> str:
    """The instruction, built from this invocation's state (the verdict payload and the asset). A
    callable, so ADK's {key} templating is bypassed and the LogQL braces are sent as written."""
    verdict = dict(ctx.state.get(STATE_VERDICT) or {})
    asset = ctx.state.get(STATE_ASSET) or {}
    run_id = verdict.get("run_id") or asset.get("run_id") or ctx.invocation_id
    asset_id = verdict.get("asset_id") or asset.get("asset_id") or "unknown-asset"
    kind = investigation_kind(verdict)
    focus = gates_to_investigate(verdict)
    # This run's own resolution first (what the verdict actually asked Grafana with); the pins next;
    # a bare default only if the verdict never got that far (an early instrument error).
    resolved = verdict.get("datasources") or {}
    loki_uid = resolved.get("loki_uid") or pinned_loki_uid() or "grafanacloud-logs"
    prom_uid = resolved.get("prom_uid") or pinned_prometheus_uid() or "grafanacloud-prom"
    gate_lines = []
    for g in verdict.get("gates") or []:
        seen = g.get("seen_this_run")
        gate_payload = ctx.state.get(STATE_GATE.format(g.get("gate"))) or {}
        muted = bool(gate_payload.get("telemetry_muted"))
        gate_lines.append(f'- {g.get("gate")}: {g.get("status")}, "{str(g.get("reason", ""))[:240]}"; '
                          f'seen by Grafana for this run: {"yes" if seen else "NO" if seen is False else "unknown"}; '
                          f'calibrated: {"yes" if g.get("calibrated") else "no"} ({g.get("calibration", "")})'
                          + ("; telemetry muted by the reviewer for this run: yes (the gate ran and pushed nothing, so Loki holds no line for it "
                             "on purpose; that is the cause, not an outage)" if muted else ""))
    reasons = "\n".join(f"- {r[:300]}" for r in verdict.get("reasons") or []) or "- (none)"
    if kind == "ROOT CAUSE":
        task = (f"The verdict BLOCKED because a control was unavailable, uncalibrated or in error: {', '.join(focus)}. "
                "Read this run's line of each such gate (its reasons name the failure; a fault field means the failure was injected on purpose "
                "by the reviewer), then that gate's previous runs over the last 24 hours to say whether the failure is new or recurring, "
                "then the alert rules to say whether an Airlock rule is firing or pending. Name the root cause: what failed, "
                "in which gate, at what time (time_utc of the line), and whether it was injected or real.")
    elif verdict.get("status") == "PASS":
        task = ("The verdict is PASS: every gate passed, was seen by Grafana for this run, and is calibrated. Read this run's line of "
                f"{focus[0]} and of {focus[-1]}, confirm they carry this run id, then the alert rules to say whether any Airlock alert "
                "rule fires. The note says what was checked and rests on the time_utc of the latest line read.")
    else:
        task = (f"The verdict BLOCKED on the content of the asset: {', '.join(focus)}. Read this run's line of each blocking gate and name, "
                "with its time_utc, the finding and the rule id it cites (rule_ids in the line); say whether a human can lift the block "
                "with paperwork (a substantiation, a licence, a release) or whether the asset does not meet the charter or registry it was "
                "checked against. The charter (charter.yaml) is this demo's own brand book, not a universal standard: when a brand finding "
                "is the block, say it does not meet THIS charter, not that the asset itself is wrong.")
    trace_line = (f"\ntrace id: {verdict['trace_id']} (this run's trace in Tempo; the Loki lines of this run carry it as the body field trace_id, "
                  "not a label: filter with |= if you need it; you may cite it)" if verdict.get("trace_id") else "")
    return f"""You are the investigator of Airlock, a release control for generated video ads. Four gates (rights, claim, brand, provenance)
read the asset, then a deterministic verdict asked Grafana about each gate and ruled. The verdict is final; you do not change it.
You explain it from what Grafana holds, for the human who receives the incident or reads the record.

RUN
asset: {asset_id}
run id: {run_id}{trace_line}
verdict: {verdict.get("status")} ({verdict.get("motive")}), needs a human: {"yes" if verdict.get("needs_human") else "no"}
reasons:
{reasons}
gates:
{chr(10).join(gate_lines) or "- (no gate lines)"}

TOOLS, at most {INVESTIGATION_TOOL_BUDGET} calls in total, never the same call twice
- query_loki_logs(datasourceUid="{loki_uid}", logql=<LogQL>, startRfc3339="now-1h", endRfc3339="now", limit=20): Loki holds one JSON
  line per gate run, with the fields asset_id, run_id, gate, status, reasons, rule_ids, elapsed_ms, evidence_head and, when the reviewer
  injected a fault, fault. Every line carries time_utc: cite it as written.
  this run, one gate:            {{app="airlock", gate="rights"}} |= "{run_id}"
  previous runs of a gate:       {{app="airlock", gate="rights"}} with startRfc3339="now-24h" (newest first)
  the errors of a gate:          {{app="airlock", gate="rights", status="ERROR"}} with startRfc3339="now-24h"
- query_prometheus(datasourceUid="{prom_uid}", expr=<PromQL>, queryType="instant", endTime="now"): the counters the gates push, e.g.
  sum(sum_over_time(airlock_gate_errors_total{{gate="rights"}}[15m])) and sum(sum_over_time(airlock_gate_runs_total{{gate="rights"}}[15m])).
- alerting_manage_rules(operation="list", label_selectors=['{{app="airlock"}}']): the five Airlock alert rules, "Airlock gate errors",
  "Airlock daily proof failed", "Airlock calibration missed", "Airlock verdict could not reach Grafana", "Airlock daily proof did not run",
  with their state (firing, pending, normal, unknown). Read only: never another operation.

TASK
{task}
Then write the note: at most {INVESTIGATION_NOTE_WORDS} words, plain English for a non-engineer, every fact taken from a tool answer, the
time_utc of the log line the note rests on quoted as written. Say it when an alert rule fires or is pending. If a tool answered an error,
say so and rest on what you have. Never invent a line, a value or a timestamp. The note ends with exactly one line that starts with
"{kind}: " and names the cause (or the decision) in one sentence."""


def compact_loki_answer(text: str) -> str:
    """The query_loki_logs answer as the model reads it: each row gains time_utc (the nanosecond timestamp
    read as UTC, the timestamp the note cites) and its body's evidence is cut to a head, so twenty lines
    of the rights gate do not carry twenty logo tables. Anything that is not the JSON shape is returned as is."""
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        return text
    rows = d.get("data") if isinstance(d, dict) else None
    if not isinstance(rows, list):
        return text
    for row in rows:
        if not isinstance(row, dict):
            continue
        row["time_utc"] = loki_timestamp(row.get("timestamp"))
        raw_line = row.get("line")
        if not isinstance(raw_line, str):
            continue
        try:
            body = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(body, dict) and "evidence" in body:
            evidence = json.dumps(body.pop("evidence"), default=str)
            body["evidence_head"] = evidence[:EVIDENCE_HEAD_CHARS] + ("..." if len(evidence) > EVIDENCE_HEAD_CHARS else "")
            row["line"] = json.dumps(body, default=str)
    return json.dumps(d, default=str)


def loki_lines_from_answer(text: str) -> list[dict[str, Any]]:
    """The compact Loki lines of a query_loki_logs answer: time_utc, gate, status, run_id, asset_id, the first
    reason and the fault, for the incident body and the record."""
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        return []
    rows = d.get("data") if isinstance(d, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("line"), str):
            continue
        try:
            body = json.loads(row["line"])
        except json.JSONDecodeError:
            continue
        if not isinstance(body, dict):
            continue
        labels = row.get("labels") or {}
        entry: dict[str, Any] = {"time_utc": row.get("time_utc") or loki_timestamp(row.get("timestamp")),
                                 "gate": body.get("gate") or labels.get("gate"),
                                 "status": body.get("status") or labels.get("status"),
                                 "run_id": body.get("run_id"), "asset_id": body.get("asset_id"),
                                 "reason": str((body.get("reasons") or [""])[0])[:240]}
        if body.get("fault"):
            entry["fault"] = body["fault"]
        out.append(entry)
    return out


def format_loki_line(entry: dict[str, Any]) -> str:
    fault = f" (fault: {entry['fault']})" if entry.get("fault") else ""
    return f"{entry.get('time_utc')} {entry.get('gate')} {entry.get('status')}{fault}: {entry.get('reason')} [run {entry.get('run_id')}]"


def note_kind_line(text: str, kind: str) -> str | None:
    """The one line of the note that starts with the kind ("ROOT CAUSE: ..."), or None when the model left it out."""
    for raw in reversed(text.splitlines()):
        stripped = raw.strip().lstrip("*# ").strip()
        if stripped.upper().startswith(kind + ":"):
            return stripped
    return None


def strip_markdown(text: str) -> str:
    """The Record renders this note as plain text, not markdown: drop the syntax a model reaches for
    (bold, headings, backticks) rather than the words themselves. Found live, 2026-09-05: a note
    showed literal asterisks and backticks to the reviewer."""
    out = re.sub(r"\*\*(.+?)\*\*", lambda m: m.group(1), text)
    out = re.sub(r"`([^`]+)`", lambda m: m.group(1), out)
    out = re.sub(r"^#{1,6}\s*", "", out, flags=re.MULTILINE)
    return out


def enforce_note_budget(text: str, kind: str, limit: int = INVESTIGATION_NOTE_WORDS) -> tuple[str, int | None]:
    """The instruction asks for at most `limit` words; a model that ignores it gets truncated to its own
    conclusion line rather than shown whole (found live, 2026-09-05: a 242 word note against a 60 word
    ask). Returns the text to use and the original word count when it overran, else None."""
    text = strip_markdown(text)
    words = text.split()
    if len(words) <= limit:
        return text, None
    conclusion = note_kind_line(text, kind)
    return (conclusion or " ".join(words[: limit + 5]) + " (truncated)"), len(words)


def cited_lines(note: str, lines: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    """The Loki lines the note rests on: those whose time_utc the note quotes, then this run's lines, deduplicated."""
    seen: set[str] = set()
    picked: list[dict[str, Any]] = []
    for entry in lines:
        key = f"{entry.get('time_utc')}|{entry.get('gate')}|{entry.get('run_id')}"
        if key in seen:
            continue
        stamp = str(entry.get("time_utc") or "")
        if (stamp and stamp in note) or (stamp[:19] and stamp[:19] in note) or entry.get("run_id") == run_id:
            seen.add(key)
            picked.append(entry)
    return picked[:LOKI_LINES_KEPT]


def fallback_note(kind: str, verdict: dict[str, Any], error: str) -> str:
    """The deterministic note when the investigator could not run: the verdict's own first reason, and why."""
    first = (verdict.get("reasons") or ["no reason recorded"])[0]
    return f"investigation unavailable: {error[:300]}\n{kind}: {first[:300]} (from the verdict, not investigated)"


class InvestigationBudget:
    """The bounds of one investigation: tool calls, model turns and wall time, enforced through the
    LlmAgent's callbacks. Past the tool budget the tool answers a refusal; past the model or time
    budget the model turn is replaced by a closing note, which ends the loop."""

    def __init__(self, kind: str, tool_calls: int = INVESTIGATION_TOOL_BUDGET, model_calls: int = INVESTIGATION_MODEL_CALLS,
                 budget_s: float = INVESTIGATION_BUDGET_S) -> None:
        self.kind = kind
        self.max_tool_calls = tool_calls
        self.max_model_calls = model_calls
        self.deadline = time.monotonic() + budget_s
        self.tool_calls = 0
        self.model_calls = 0
        self.stopped: str | None = None

    def before_tool(self, tool: Any, args: dict[str, Any], tool_context: Any) -> dict[str, Any] | None:
        self.tool_calls += 1
        if self.tool_calls > self.max_tool_calls:
            self.stopped = self.stopped or f"tool budget of {self.max_tool_calls} calls spent"
            return {"error": f"tool budget of {self.max_tool_calls} calls spent: write the note now from the answers you have"}
        if getattr(tool, "name", "") == "alerting_manage_rules" and str(args.get("operation", "list")) not in ALERT_RULE_READ_OPERATIONS:
            # The investigator reads; it never creates, updates or deletes a rule, whatever the model asks.
            return {"error": f"alerting_manage_rules is read only here: operation {args.get('operation')!r} refused, use operation 'list'"}
        return None

    def after_tool(self, tool: Any, args: dict[str, Any], tool_context: Any, tool_response: Any) -> dict[str, Any] | None:
        """query_loki_logs answers gain time_utc and lose their evidence tables before the model reads them."""
        if getattr(tool, "name", "") != "query_loki_logs" or not isinstance(tool_response, dict):
            return None
        parts = tool_response.get("content")
        if not isinstance(parts, list):
            return None
        changed = dict(tool_response)
        changed["content"] = [{**p, "text": compact_loki_answer(p["text"])} if isinstance(p, dict) and isinstance(p.get("text"), str) else p for p in parts]
        return changed

    def on_tool_error(self, tool: Any, args: dict[str, Any], tool_context: Any, error: Exception) -> dict[str, Any]:
        """A tool that raised answers its error as text: the model says so in the note instead of the run dying."""
        return {"error": f"{getattr(tool, 'name', 'tool')} failed: {type(error).__name__}: {str(error)[:400]}"}

    def before_model(self, callback_context: Any, llm_request: Any) -> LlmResponse | None:
        self.model_calls += 1
        if self.model_calls > self.max_model_calls:
            self.stopped = self.stopped or f"model budget of {self.max_model_calls} turns spent"
        elif time.monotonic() > self.deadline:
            self.stopped = self.stopped or f"time budget of {INVESTIGATION_BUDGET_S} s spent"
        else:
            return None
        text = f"{self.kind}: investigation stopped, {self.stopped}; the verdict stands on its own reasons."
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))

    def on_model_error(self, callback_context: Any, llm_request: Any, error: Exception) -> LlmResponse:
        self.stopped = f"model error: {type(error).__name__}: {str(error)[:200]}"  # the error that ended it, whatever came before
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=f"investigation unavailable: {self.stopped}")]))


def make_investigator(budget: InvestigationBudget, toolset: McpToolset) -> LlmAgent:
    """The LlmAgent, built per run so that its toolset is this run's and closed with it."""
    return LlmAgent(
        name="investigator",
        model=INVESTIGATOR_MODEL,
        description="reads this run's Loki lines, the gate counters and the alert rules through mcp-grafana and names the cause",
        instruction=investigator_instruction,
        tools=[toolset],
        output_key=INVESTIGATION_OUTPUT_KEY,
        include_contents="none",  # the instruction carries the run; the history of the four gates is not re-sent
        generate_content_config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=INVESTIGATION_OUTPUT_TOKENS,
                                                            thinking_config=types.ThinkingConfig(thinking_budget=INVESTIGATION_THINKING_TOKENS,
                                                                                                 include_thoughts=False)),
        before_tool_callback=budget.before_tool,
        after_tool_callback=budget.after_tool,
        on_tool_error_callback=budget.on_tool_error,
        before_model_callback=budget.before_model,
        on_model_error_callback=budget.on_model_error,
    )


def tool_rows(event: Event) -> list[dict[str, Any]]:
    """The investigator's tool calls and answers as rows: one per function_call part and one per function_response part."""
    rows: list[dict[str, Any]] = []
    for part in (event.content.parts if event.content and event.content.parts else []):
        fc = getattr(part, "function_call", None)
        if fc is not None and fc.name:
            rows.append({"step": "tool_call", "tool": fc.name, "args": dict(fc.args or {})})
        fr = getattr(part, "function_response", None)
        if fr is not None and fr.name:
            text = tool_text(fr.response if isinstance(fr.response, (dict, list)) else str(fr.response))
            row: dict[str, Any] = {"step": "tool_result", "tool": fr.name, "chars": len(text), "preview": text[:240]}
            if fr.name == "query_loki_logs":
                lines = loki_lines_from_answer(text)
                row["lines"] = len(lines)
                row["loki_lines"] = lines
            rows.append(row)
    return rows


class InvestigationAgent(BaseAgent):
    """Runs the investigator LlmAgent on every verdict, streams its tool calls as rows, and turns any
    failure into a fallback note: the run never stops here, and the escalation reads the note from state."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        verdict = ctx.session.state.get(STATE_VERDICT) or {}
        run_id = str(verdict.get("run_id") or ctx.invocation_id)
        kind = investigation_kind(verdict)
        started = time.time()
        budget = InvestigationBudget(kind)
        calls: list[dict[str, Any]] = []
        loki_lines: list[dict[str, Any]] = []
        text = ""
        error: str | None = None
        toolset: McpToolset | None = None
        try:
            toolset = make_grafana_toolset(INVESTIGATION_TOOLS)
            investigator = make_investigator(budget, toolset)
            async with asyncio.timeout(INVESTIGATION_BUDGET_S + 30):
                async for event in investigator.run_async(ctx):
                    for row in tool_rows(event):
                        loki_lines.extend(row.pop("loki_lines", []))
                        calls.append(row)
                        yield _text_event(ctx, self.name, json.dumps({"stage": "investigation", "run_id": run_id, **row}, default=str),
                                          isolation_scope=INVESTIGATION_ROW_SCOPE)
                    if event.content and event.content.parts and event.is_final_response():
                        text = "".join(p.text or "" for p in event.content.parts if getattr(p, "text", None))
                    yield event  # the LlmAgent's own events: the runner appends them, the model's next turn reads them
        except Exception as exc:  # the investigation is an explanation, never a gate: it fails into a note
            error = f"{type(exc).__name__}: {str(exc)[:300]}"
        finally:
            if toolset is not None:
                try:
                    await toolset.close()
                except Exception:
                    pass
        text = text.strip()
        if error and not text:
            text = fallback_note(kind, verdict, error)
        elif not text:
            text = fallback_note(kind, verdict, budget.stopped or "the model returned no text")
        # The instruction asks for at most INVESTIGATION_NOTE_WORDS words and plain text; the model does
        # not always keep either promise (measured live, 2026-09-05: 242 words with markdown syntax against
        # a 60 word plain-text ask). Enforced here rather than trusted, and the overrun is said, not hidden.
        note, overran_words = enforce_note_budget(text, kind)
        payload: dict[str, Any] = {"stage": "investigation", "kind": kind, "note": note, "run_id": run_id,
                                   "asset_id": verdict.get("asset_id"), "model": INVESTIGATOR_MODEL,
                                   "tool_calls": sum(1 for c in calls if c.get("step") == "tool_call"),
                                   "model_turns": budget.model_calls, "steps": calls,
                                   "loki_lines": loki_lines[:LOKI_LINES_KEPT * 3],
                                   "cited": cited_lines(note, loki_lines, run_id),
                                   "conclusion": note_kind_line(note, kind),
                                   "elapsed_ms": int((time.time() - started) * 1000)}
        if overran_words:
            payload["note_words_before_truncation"] = overran_words
        if error or note.startswith("investigation unavailable"):
            payload["fallback"] = True
            payload["error"] = error or budget.stopped
        if budget.stopped:
            payload["stopped"] = budget.stopped
        yield _text_event(ctx, self.name, json.dumps(payload, default=str), state_delta={STATE_INVESTIGATION: payload, INVESTIGATION_OUTPUT_KEY: note})


# Who owns the BLOCK. Paperwork (a substantiation, a licence, a release, a signer to trust) goes to the
# clearance owner; the state of a control (R1, R2, instrument error) goes to the platform.
OWNER_CLEARANCE = "clearance"
OWNER_PLATFORM = "platform"
CLEARANCE_ROUTING = "Route to the clearance owner (legal or agency): a licence, a release or a study lifts this block"
PLATFORM_ROUTING = "Route to the platform owner: a control was unavailable, uncalibrated or in error; the asset was not judged"


def incident_owner(verdict: dict[str, Any]) -> str:
    if verdict.get("motive") == "content" and needs_paperwork(list(verdict.get("rule_ids") or [])):
        return OWNER_CLEARANCE
    return OWNER_PLATFORM


def incident_title(verdict: dict[str, Any], asset_id: str) -> str:
    return f"Airlock needs a human: {verdict.get('motive')} on {asset_id}"[:120]


def incident_url(incident_id: str, path: str | None = None) -> str | None:
    """The incident's page on the stack: Grafana Incident answers a relative overviewURL, the console
    needs an absolute one; None when GRAFANA_URL is not set (a local run without it)."""
    base = settings.grafana_url().rstrip("/")
    if path and path.startswith("http"):
        return path
    if not base:
        return None
    return base + (path if path and path.startswith("/") else f"/a/grafana-irm-app/incidents/{incident_id}")


def find_open_incident(list_text: str, title: str) -> dict[str, Any] | None:
    """The newest active incident of a list_incidents answer whose title is exactly this one (same asset, same motive)."""
    try:
        d = json.loads(list_text)
    except json.JSONDecodeError:
        return None
    items = d.get("incidents") if isinstance(d, dict) else d
    if not isinstance(items, list):
        return None
    matches = [i for i in items if isinstance(i, dict) and i.get("title") == title and str(i.get("status", "active")).lower() == "active"]
    if not matches:
        return None
    matches.sort(key=lambda i: str(i.get("createdTime") or ""), reverse=True)
    return matches[0]


# Grafana Incident refuses an attachCaption over 512 characters (measured 2026-09-05: "oto: validation: AttachCaption is too long (max 512)").
INCIDENT_CAPTION_MAX = 500


def incident_caption(verdict: dict[str, Any], investigation: dict[str, Any], owner: str) -> str:
    """The short caption on the incident: the routing line and the investigator's conclusion (or the
    verdict's first reason); the full note and the Loki lines go in the incident's first timeline note."""
    routing = CLEARANCE_ROUTING if owner == OWNER_CLEARANCE else PLATFORM_ROUTING
    conclusion = investigation.get("conclusion") or (verdict.get("reasons") or ["no reason recorded"])[0]
    return f"{routing}. {conclusion}"[:INCIDENT_CAPTION_MAX]


def incident_body(verdict: dict[str, Any], investigation: dict[str, Any], owner: str) -> str:
    """What the incident carries: the routing line, the run and its trace, the investigator's note, the Loki lines it
    cites, the verdict's reasons."""
    routing = CLEARANCE_ROUTING if owner == OWNER_CLEARANCE else PLATFORM_ROUTING
    parts = [f"{routing}.",
             f"Run {verdict.get('run_id')} on {verdict.get('asset_id')}: {verdict.get('status')} ({verdict.get('motive')})."]
    if verdict.get("trace_url"):
        parts.append(f"Trace: {verdict['trace_url']}")
    parts += ["", f"Investigation ({investigation.get('model', INVESTIGATOR_MODEL)}, {investigation.get('tool_calls', 0)} tool calls):",
              str(investigation.get("note") or "no note")]
    cited = investigation.get("cited") or []
    if cited:
        parts += ["", "Loki lines:"] + [f"- {format_loki_line(e)}" for e in cited]
    parts += ["", "Reasons:"] + [f"- {r[:300]}" for r in verdict.get("reasons") or []]
    return "\n".join(parts)[:4000]


class EscalationAgent(BaseAgent):
    """On a BLOCK only a human can arbitrate (paperwork missing, or a control unavailable, uncalibrated or
    in error), opens a Grafana incident, or attaches this run to the open incident of the same asset and
    motive, with the investigator's note and the Loki lines it cites. A content BLOCK on a defect of the
    asset itself needs no human: the rule already decided."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        verdict = ctx.session.state.get(STATE_VERDICT) or {}
        investigation = ctx.session.state.get(STATE_INVESTIGATION) or {"note": ctx.session.state.get(INVESTIGATION_OUTPUT_KEY), "tool_calls": 0}
        asset_id = verdict.get("asset_id", "unknown-asset")
        if not verdict.get("needs_human"):
            yield _text_event(ctx, self.name, json.dumps({"stage": "escalation", "opened": False,
                                                          "reason": f"no human needed: verdict {verdict.get('status', '?')} on {verdict.get('motive', '?')}"}))
            return
        toolset = make_grafana_toolset(["list_incidents", "create_incident", "add_activity_to_incident", "create_annotation"])
        tool_ctx = Context(invocation_context=ctx)
        started = time.time()
        owner = incident_owner(verdict)
        title = incident_title(verdict, asset_id)
        body = incident_body(verdict, investigation, owner)
        drill = settings.incident_drill()
        motive_label = str(verdict.get("motive", "")).replace(" ", "-")
        try:
            tools = {t.name: t for t in await toolset.get_tools(tool_ctx)}

            async def call(name: str, args: dict[str, Any]) -> str:
                with tracing.span(f"grafana.{name}", tool=name, run_id=verdict.get("run_id")):
                    return tool_text(await tools[name].run_async(args=args, tool_context=tool_ctx))

            reasons = verdict.get("reasons", [])
            payload: dict[str, Any] = {"stage": "escalation", "opened": False, "attached": False, "owner": owner, "title": title}
            existing = None
            try:
                listed = await call("list_incidents", {"status": "active", "drill": drill, "limit": 50})
                existing = find_open_incident(listed, title)
            except Exception as exc:  # a list that fails means a new incident, said in the payload
                payload["list_error"] = f"{type(exc).__name__}: {exc}"[:300]
            if existing:
                incident_id = str(existing.get("incidentId") or existing.get("incidentID"))
                act = await call("add_activity_to_incident", {"incidentId": incident_id, "body": body})
                payload.update({"attached": True, "incident_id": incident_id, "incident_title": existing.get("title"),
                                "incident_url": incident_url(incident_id), "activity_raw": act[:300]})
                try:
                    payload["activity_id"] = json.loads(act).get("activityItemID")
                except (json.JSONDecodeError, AttributeError):
                    pass
            else:
                inc = await call("create_incident", {
                    "title": title,
                    "severity": "minor",
                    "roomPrefix": "airlock",
                    "status": "active",
                    "isDrill": drill,
                    "labels": [{"key": "airlock", "label": motive_label}, {"key": "owner", "label": owner}],
                    "attachCaption": incident_caption(verdict, investigation, owner)})
                payload.update({"opened": True, "incident_raw": inc[:500]})
                try:
                    d = json.loads(inc)
                    incident = d.get("incident") or d
                    payload["incident_id"] = incident.get("incidentID") or incident.get("id")
                    payload["incident_url"] = incident_url(str(payload["incident_id"]),
                                                           incident.get("overviewURL") or incident.get("incidentURL") or incident.get("url"))
                    payload["incident_title"] = incident.get("title")
                except (json.JSONDecodeError, AttributeError):
                    pass
                if payload.get("incident_id"):
                    # The full note as the incident's first timeline entry: the caption is short, the timeline is not.
                    try:
                        act = await call("add_activity_to_incident", {"incidentId": str(payload["incident_id"]), "body": body})
                        payload["activity_id"] = json.loads(act).get("activityItemID")
                    except Exception as exc:
                        payload["activity_error"] = f"{type(exc).__name__}: {exc}"[:300]
            if not payload.get("incident_id"):
                # The plan's fallback: the Incident API refused (a free stack whose Incident app was never
                # opened answers a foreign-key error). A second annotation tagged needs-human carries the
                # hand-off instead, and the console shows the approval button. Said here, not hidden.
                payload["opened"] = False
                payload["fallback"] = "needs-human annotation"
                ann = await call("create_annotation", {
                    "dashboardUid": settings.dashboard_uid(),
                    "time": int(time.time() * 1000),
                    "text": f"NEEDS HUMAN ({verdict.get('motive')}, owner {owner}) {asset_id}: " + " | ".join(reasons)[:800],
                    "tags": ["airlock", "needs-human", f"owner:{owner}", asset_id[:40], settings.runtime()]})
                try:
                    payload["fallback_annotation_id"] = json.loads(ann).get("Payload", {}).get("id")
                except (json.JSONDecodeError, AttributeError):
                    payload["fallback_annotation_raw"] = ann[:300]
            payload["elapsed_ms"] = int((time.time() - started) * 1000)
            if shared_pushers()[0] is not None:
                try:
                    push_incident_sample(str(verdict.get("status", "BLOCK")), str(verdict.get("motive", "")), owner, attached=bool(payload.get("attached")))
                except Exception as exc:
                    payload["telemetry_error"] = f"{type(exc).__name__}: {exc}"
            yield _text_event(ctx, self.name, json.dumps(payload, default=str), state_delta={"temp:airlock:escalation": payload})
        except Exception as exc:
            yield _text_event(ctx, self.name, json.dumps({"stage": "escalation", "opened": False, "error": f"{type(exc).__name__}: {exc}"}))
            raise
        finally:
            await toolset.close()


def push_incident_sample(status: str, motive: str, owner: str, attached: bool) -> None:
    """The incident samples, pushed from the escalation only (the verdict's sample no longer carries an
    always-zero incidents_total): airlock_incident{motive, owner} total=1 (attached=1 when this run joined an
    open incident) and airlock_verdict{status, motive} incidents_total=1."""
    motive_tag = motive.replace(" ", "_")
    influx, _ = shared_pushers()
    if influx is None:
        return
    influx.push_lines([
        line("airlock_incident", {"motive": motive_tag, "owner": owner}, {"total": 1, "attached": 1 if attached else 0}),
        line("airlock_verdict", {"status": status, "motive": motive_tag}, {"incidents_total": 1}),
    ])


gate_agents: list[BaseAgent] = [GateAgent(name=f"{g}_gate", gate=g, description=f"{g} gate: {CHECKS[g][1]}") for g in GATES]
gates = ParallelAgent(name="gates", sub_agents=gate_agents, description="the four gates, in parallel")
verdict = VerdictAgent(name="verdict", description="asks Grafana about each gate, decides, writes the annotation")
investigation = InvestigationAgent(
    name="investigation",
    description="an LlmAgent on gemini-2.5-flash reads Loki, the counters and the alert rules through mcp-grafana and names the cause")
escalation = EscalationAgent(name="escalation",
                             description="opens or joins a Grafana incident, with the investigator's note, when only a human can arbitrate the BLOCK")
root_agent = SequentialAgent(name="airlock", sub_agents=[gates, verdict, investigation, escalation],
                             description="Airlock: ship or block a generated asset on proof")
