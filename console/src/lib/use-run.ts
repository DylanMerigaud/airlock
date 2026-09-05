"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { loadLastRun, saveLastRun } from "@/lib/last-run";
import {
  GATE_ORDER,
  GATE_SOURCE_OF_TRUTH,
  GATE_STEP,
  parsePayload,
  type ChipStatus,
  type EscalationPayload,
  type FaultMap,
  type GateDonePayload,
  type GateName,
  type InvestigationPayload,
  type InvestigationStepPayload,
  type ProbePayload,
  type ReportedInstrument,
  type VerdictPayload,
} from "@/lib/events";

export type GateCardState = {
  gate: GateName;
  status: ChipStatus;
  sourceOfTruth: string;
  done: GateDonePayload | null;
  probe: ProbePayload | null;
  /** The gate ran but pushed nothing to Grafana on this run. */
  muted: boolean;
  /** The fault injected into this gate for this run ("timeout"), or null. */
  fault: string | null;
  /** The ADK invocation id the gate reported, when it did. */
  runId: string | null;
  /** Health and calibration as the verdict agent read them, when it sent them. */
  reported: ReportedInstrument | null;
  /** The order this gate reported in, so the findings thread reads oldest first. */
  settledAt: number | null;
  /** Wall clock (ms since epoch) when the gate started running, for the elapsed counter. */
  runningSince: number | null;
};

export type RowTone = "neutral" | "pass" | "block" | "amber";

export type TimelineRow = {
  key: string;
  author: string;
  ts: number;
  line: string;
  tone: RowTone;
  raw: string;
  muted?: boolean;
  /** The fault injected into the gate this row belongs to, when one was. */
  fault?: string;
  /** A remark about Grafana itself (a paused stack waking), not about a gate. */
  grafanaNote?: string;
  verdict?: VerdictPayload;
  /** A tool call or a tool answer of the investigator, when this row is one. */
  investigationStep?: InvestigationStepPayload;
  investigation?: InvestigationPayload;
  escalation?: EscalationPayload;
};

export type RunPhase = "idle" | "running" | "settled" | "lost";

export type RunState = {
  phase: RunPhase;
  target: string | null;
  /** The gates whose telemetry was muted when this run started. */
  muted: GateName[];
  /** The faults injected when this run started, gate by gate. */
  faults: FaultMap;
  /** What the verdict said about Grafana itself, when it said anything (a wake). */
  grafanaNotes: string[];
  step: string | null;
  rows: TimelineRow[];
  gates: Record<GateName, GateCardState>;
  verdict: VerdictPayload | null;
  /** The investigator's note, when it has landed (every verdict gets one, a fallback at worst). */
  investigation: InvestigationPayload | null;
  /** The investigator's tool calls so far, oldest first. */
  investigationSteps: InvestigationStepPayload[];
  escalation: EscalationPayload | null;
  verdictStatus: ChipStatus;
  investigationStatus: ChipStatus;
  escalationStatus: ChipStatus;
  failure: string | null;
  elapsedMs: number | null;
  startedAt: number | null;
  /** Restored from this tab's sessionStorage on mount, not produced by a live stream. */
  restored?: boolean;
};

function freshGates(muted: GateName[] = [], faults: FaultMap = {}): Record<GateName, GateCardState> {
  return GATE_ORDER.reduce(
    (acc, gate) => {
      acc[gate] = {
        gate,
        status: "PENDING",
        sourceOfTruth: GATE_SOURCE_OF_TRUTH[gate],
        done: null,
        probe: null,
        muted: muted.includes(gate),
        fault: faults[gate] ?? null,
        runId: null,
        reported: null,
        settledAt: null,
        runningSince: null,
      };
      return acc;
    },
    {} as Record<GateName, GateCardState>,
  );
}

/**
 * A run restored from sessionStorage may predate a field: fill what is
 * missing so the components never read undefined where a null is promised.
 */
function withDefaults(run: RunState): RunState {
  const gates = { ...run.gates };
  for (const gate of GATE_ORDER) {
    const card = gates[gate];
    if (!card) continue;
    gates[gate] = { ...card, fault: card.fault ?? null, runId: card.runId ?? null };
  }
  return {
    ...run,
    faults: run.faults ?? {},
    grafanaNotes: run.grafanaNotes ?? [],
    investigation: run.investigation ?? null,
    investigationSteps: run.investigationSteps ?? [],
    investigationStatus: run.investigationStatus ?? "PENDING",
    gates,
  };
}

export const IDLE_STATE: RunState = {
  phase: "idle",
  target: null,
  muted: [],
  faults: {},
  grafanaNotes: [],
  step: null,
  rows: [],
  gates: freshGates(),
  verdict: null,
  investigation: null,
  investigationSteps: [],
  escalation: null,
  verdictStatus: "PENDING",
  investigationStatus: "PENDING",
  escalationStatus: "PENDING",
  failure: null,
  elapsedMs: null,
  startedAt: null,
};

function pretty(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

function toneFor(status: string | undefined): RowTone {
  if (status === "PASS") return "pass";
  if (status === "BLOCK" || status === "ERROR") return "block";
  return "neutral";
}

export function escalationLine(payload: EscalationPayload): string {
  if (payload.attached && payload.incident_id) {
    return `Joined open incident ${payload.incident_id}${payload.incident_title ? `: ${payload.incident_title}` : ""} (same asset, same motive) with the investigator's note`;
  }
  if (payload.incident_id) {
    return `Incident ${payload.incident_id} opened${payload.incident_title ? `: ${payload.incident_title}` : ""}${
      payload.owner ? `, routed to the ${payload.owner} owner` : ""
    }`;
  }
  if (payload.fallback_annotation_id !== undefined) {
    return `The Incident API refused, a needs-human annotation was written instead (id ${payload.fallback_annotation_id})`;
  }
  if (payload.opened && payload.incident_raw) {
    return "The Incident API refused to open an incident. The refusal is recorded below.";
  }
  if (payload.reason) return payload.reason;
  return payload.opened ? "Incident opened." : "No escalation needed.";
}

/** One line for a tool call or a tool answer of the investigator. */
export function investigationStepLine(payload: InvestigationStepPayload): string {
  if (payload.step === "tool_call") {
    const args = payload.args ?? {};
    const detail =
      typeof args.logql === "string"
        ? args.logql
        : typeof args.expr === "string"
          ? args.expr
          : typeof args.operation === "string"
            ? `operation ${args.operation}`
            : "";
    return `Investigator calls ${payload.tool}${detail ? `: ${detail}` : ""}`;
  }
  const lines = payload.lines !== undefined ? `, ${payload.lines} log line${payload.lines === 1 ? "" : "s"}` : "";
  return `${payload.tool} answered${payload.chars !== undefined ? ` (${payload.chars} chars${lines})` : ""}`;
}

/** The one line of the note that carries its conclusion, or the note's first line. */
export function investigationLine(payload: InvestigationPayload): string {
  const first = payload.note.split("\n")[0];
  if (payload.fallback) return first || "Investigation unavailable.";
  return payload.conclusion ?? first ?? payload.note;
}

export type RunHandle = {
  state: RunState;
  start: (asset: string, mute?: GateName[], faults?: FaultMap) => void;
  retry: (mute?: GateName[], faults?: FaultMap) => void;
  busy: boolean;
};

export function useRun(): RunHandle {
  const [state, setState] = useState<RunState>(IDLE_STATE);
  const abortRef = useRef<AbortController | null>(null);
  const lastTarget = useRef<string | null>(null);
  const counter = useRef(0);

  // The last settled run of this tab comes back on mount, and every settled run
  // is written as it lands, so leaving the page for Grafana loses nothing.
  useEffect(() => {
    const previous = loadLastRun();
    if (!previous) return;
    lastTarget.current = previous.target;
    const restored = withDefaults(previous);
    setState((current) => (current.phase === "idle" ? restored : current));
  }, []);

  useEffect(() => {
    if (state.phase === "settled" && !state.restored) saveLastRun(state);
  }, [state]);

  const start = useCallback((asset: string, mute: GateName[] = [], faultsAsked: FaultMap = {}) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    lastTarget.current = asset;
    counter.current = 0;
    const muted = GATE_ORDER.filter((gate) => mute.includes(gate));
    const faults: FaultMap = {};
    for (const gate of GATE_ORDER) {
      if (faultsAsked[gate]) faults[gate] = faultsAsked[gate];
    }
    const startedAt = Date.now();

    setState({
      ...IDLE_STATE,
      gates: freshGates(muted, faults),
      phase: "running",
      target: asset,
      muted,
      faults,
      startedAt,
      step: "Handing the asset to the airlock pipeline",
    });

    const apply = (author: string, text: string, ts: number) => {
      const parsed = parsePayload(text);
      if (!parsed) return;
      counter.current += 1;
      const key = `${counter.current}-${author}-${ts}`;

      setState((prev) => {
        const gates = { ...prev.gates };
        let rows = prev.rows;
        let step = prev.step;
        let verdict = prev.verdict;
        let investigation = prev.investigation;
        let investigationSteps = prev.investigationSteps;
        let escalation = prev.escalation;
        let verdictStatus = prev.verdictStatus;
        let investigationStatus = prev.investigationStatus;
        let escalationStatus = prev.escalationStatus;
        let grafanaNotes = prev.grafanaNotes;
        const elapsedMs = prev.elapsedMs;

        if (parsed.kind === "gate-running") {
          const gate = parsed.gate;
          const muted = gates[gate].muted || parsed.payload.telemetry_muted === true;
          const fault = typeof parsed.payload.fault === "string" && parsed.payload.fault ? parsed.payload.fault : gates[gate].fault;
          gates[gate] = {
            ...gates[gate],
            status: "RUNNING",
            sourceOfTruth: GATE_SOURCE_OF_TRUTH[gate],
            muted,
            fault,
            runId: parsed.payload.run_id ?? gates[gate].runId,
            runningSince: Date.now(),
          };
          step = fault ? `${GATE_STEP[gate]}, with a ${fault} fault injected` : GATE_STEP[gate];
          rows = [
            ...rows,
            {
              key,
              author,
              ts,
              line: fault
                ? `Started with a ${fault} fault injected: the gate fails on purpose before it spends anything. ${GATE_STEP[gate]}`
                : `Started. ${GATE_STEP[gate]}`,
              tone: fault ? "amber" : "neutral",
              raw: pretty(text),
              muted,
              fault: fault ?? undefined,
            },
          ];
        } else if (parsed.kind === "gate-done") {
          const gate = parsed.gate;
          const muted = gates[gate].muted || parsed.payload.telemetry_muted === true;
          const fault = typeof parsed.payload.fault === "string" && parsed.payload.fault ? parsed.payload.fault : gates[gate].fault;
          gates[gate] = {
            ...gates[gate],
            status: parsed.payload.status,
            done: parsed.payload,
            muted,
            fault,
            runId: parsed.payload.run_id ?? gates[gate].runId,
            settledAt: counter.current,
          };
          const stillRunning = GATE_ORDER.filter((g) => gates[g].status === "RUNNING");
          step = stillRunning.length > 0 ? GATE_STEP[stillRunning[0]] : "Verdict agent asking Grafana about every gate";
          rows = [
            ...rows,
            {
              key,
              author,
              ts,
              line: parsed.payload.reasons?.[0] ?? `${gate} ${parsed.payload.status}`,
              tone: toneFor(parsed.payload.status),
              raw: pretty(text),
              muted,
              fault: fault ?? undefined,
            },
          ];
        } else if (parsed.kind === "grafana-note") {
          // The verdict had to wait for Grafana Cloud to wake before it could ask anything.
          const note = parsed.payload.note.trim();
          grafanaNotes = grafanaNotes.includes(note) ? grafanaNotes : [...grafanaNotes, note];
          verdictStatus = "RUNNING";
          step = note;
          rows = [
            ...rows,
            {
              key,
              author,
              ts,
              line: note,
              tone: "amber",
              raw: pretty(text),
              grafanaNote: note,
            },
          ];
        } else if (parsed.kind === "probe") {
          const gate = parsed.payload.gate;
          gates[gate] = {
            ...gates[gate],
            probe: parsed.payload,
            reported: {
              health: parsed.payload.health,
              calibrated: parsed.payload.calibrated,
              calibration: parsed.payload.calibration,
            },
          };
          verdictStatus = "RUNNING";
          step = `Asking Grafana about ${gate}`;
          const probeNote = typeof parsed.payload.note === "string" && parsed.payload.note.trim() ? parsed.payload.note.trim() : null;
          if (probeNote && !grafanaNotes.includes(probeNote)) grafanaNotes = [...grafanaNotes, probeNote];
          const unseen = parsed.payload.seen_this_run === false;
          rows = [
            ...rows,
            {
              key,
              author,
              ts,
              line: `${gate}: ${parsed.payload.health}${
                parsed.payload.calibrated ? "" : `, ${parsed.payload.calibration ?? "not calibrated"}`
              }${unseen ? ", NOT seen by Grafana for this run" : ""}${probeNote ? `. ${probeNote}` : ""}`,
              tone:
                parsed.payload.calibrated && /healthy/i.test(parsed.payload.health) && !unseen ? "neutral" : "amber",
              raw: pretty(text),
              muted: gates[gate].muted,
              fault: gates[gate].fault ?? undefined,
              grafanaNote: probeNote ?? undefined,
            },
          ];
        } else if (parsed.kind === "verdict") {
          for (const line of parsed.payload.gates ?? []) {
            const card = gates[line.gate];
            if (!card) continue;
            gates[line.gate] = {
              ...card,
              reported: {
                health: line.health ?? card.reported?.health,
                calibrated: line.calibrated ?? card.reported?.calibrated,
                calibration: line.calibration ?? card.reported?.calibration,
              },
            };
          }
          verdict = parsed.payload;
          verdictStatus = parsed.payload.status;
          // The verdict's own elapsed_ms is the Grafana round trip only; the run's wall time
          // comes with the done frame and is the number the card and the spec strip show.
          investigationStatus = "RUNNING";
          step = "Investigator reading this run's Loki lines and the alert rules through mcp-grafana";
          rows = [
            ...rows,
            {
              key,
              author,
              ts,
              line: `${parsed.payload.status}${parsed.payload.motive ? `, ${parsed.payload.motive}` : ""}`,
              tone: toneFor(parsed.payload.status),
              raw: pretty(text),
              verdict: parsed.payload,
            },
          ];
        } else if (parsed.kind === "investigation-step") {
          investigationStatus = "RUNNING";
          investigationSteps = [...investigationSteps, parsed.payload];
          step = investigationStepLine(parsed.payload);
          rows = [
            ...rows,
            {
              key,
              author,
              ts,
              line: investigationStepLine(parsed.payload),
              tone: "neutral",
              raw: pretty(text),
              investigationStep: parsed.payload,
            },
          ];
        } else if (parsed.kind === "investigation") {
          investigation = parsed.payload;
          investigationStatus = parsed.payload.fallback ? "ERROR" : "PASS";
          escalationStatus = "RUNNING";
          step = verdict?.needs_human
            ? "Escalation agent opening or joining the incident"
            : "Escalation agent: checking whether a human is needed";
          rows = [
            ...rows,
            {
              key,
              author,
              ts,
              line: investigationLine(parsed.payload),
              tone: parsed.payload.fallback ? "amber" : "neutral",
              raw: pretty(text),
              investigation: parsed.payload,
            },
          ];
        } else if (parsed.kind === "escalation") {
          escalation = parsed.payload;
          // A recording made before the investigator existed goes from verdict to escalation directly.
          if (!investigation && investigationStatus === "RUNNING") investigationStatus = "PENDING";
          escalationStatus = parsed.payload.opened || parsed.payload.attached || parsed.payload.fallback ? "BLOCK" : "PASS";
          step = null;
          rows = [
            ...rows,
            {
              key,
              author,
              ts,
              line: escalationLine(parsed.payload),
              tone: parsed.payload.opened || parsed.payload.attached || parsed.payload.fallback ? "block" : "neutral",
              raw: pretty(text),
              escalation: parsed.payload,
            },
          ];
        }

        return {
          ...prev,
          gates,
          rows,
          step,
          verdict,
          investigation,
          investigationSteps,
          escalation,
          verdictStatus,
          investigationStatus,
          escalationStatus,
          grafanaNotes,
          elapsedMs,
        };
      });
    };

    void (async () => {
      let sawDone = false;
      try {
        const response = await fetch("/api/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          // The same shape the run route hands the pipeline: mute only when a gate is
          // muted, fault only when one is injected, so a plain run stays a plain run.
          body: JSON.stringify({
            asset,
            ...(muted.length > 0 ? { mute: muted } : {}),
            ...(Object.keys(faults).length > 0 ? { fault: faults } : {}),
          }),
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          const detail = await response.text().catch(() => "");
          let message = `The run route answered ${response.status}.`;
          try {
            const parsed = JSON.parse(detail) as { error?: string };
            if (parsed.error) message = parsed.error;
          } catch {
            if (detail) message = detail.slice(0, 200);
          }
          setState((prev) => ({ ...prev, phase: "lost", step: null, failure: message }));
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let split = buffer.indexOf("\n\n");
          while (split !== -1) {
            const frame = buffer.slice(0, split);
            buffer = buffer.slice(split + 2);
            split = buffer.indexOf("\n\n");

            let eventName: string | null = null;
            const dataLines: string[] = [];
            for (const line of frame.split("\n")) {
              if (line.startsWith("event:")) eventName = line.slice(6).trim();
              else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
            }
            if (dataLines.length === 0) continue;
            let payload: unknown;
            try {
              payload = JSON.parse(dataLines.join("\n"));
            } catch {
              continue;
            }

            if (eventName === "failed") {
              const message = (payload as { message?: string }).message ?? "The run failed upstream.";
              setState((prev) => ({ ...prev, failure: message }));
            } else if (eventName === "done") {
              sawDone = true;
              const elapsed = (payload as { elapsed_ms?: number }).elapsed_ms ?? Date.now() - startedAt;
              setState((prev) => ({
                ...prev,
                phase: "settled",
                step: null,
                elapsedMs: elapsed,
                gates: GATE_ORDER.reduce(
                  (acc, gate) => {
                    acc[gate] =
                      prev.gates[gate].status === "RUNNING" || prev.gates[gate].status === "PENDING"
                        ? { ...prev.gates[gate], status: prev.failure ? "ERROR" : prev.gates[gate].status }
                        : prev.gates[gate];
                    return acc;
                  },
                  { ...prev.gates },
                ),
              }));
            } else if (eventName === "open") {
              // The relay is live. Nothing to render yet.
            } else {
              const event = payload as { author?: string; text?: string; ts?: number };
              if (event.author && typeof event.text === "string") {
                apply(event.author, event.text, event.ts ?? Date.now() - startedAt);
              }
            }
          }
        }

        if (!sawDone) {
          setState((prev) => ({
            ...prev,
            phase: "lost",
            step: null,
            failure: prev.failure ?? "The event stream closed before the run finished.",
          }));
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : String(error);
        setState((prev) => ({
          ...prev,
          phase: "lost",
          step: null,
          failure: `Connection to the run stream was lost: ${message}`,
        }));
      }
    })();
  }, []);

  const retry = useCallback(
    (mute: GateName[] = [], faults: FaultMap = {}) => {
      if (lastTarget.current) start(lastTarget.current, mute, faults);
    },
    [start],
  );

  return { state, start, retry, busy: state.phase === "running" };
}
