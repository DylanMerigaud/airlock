"use client";

import { useCallback, useRef, useState } from "react";
import {
  GATE_ORDER,
  GATE_SOURCE_OF_TRUTH,
  GATE_STEP,
  parsePayload,
  type ChipStatus,
  type EscalationPayload,
  type GateDonePayload,
  type GateName,
  type ProbePayload,
  type VerdictPayload,
} from "@/lib/events";

export type GateCardState = {
  gate: GateName;
  status: ChipStatus;
  sourceOfTruth: string;
  done: GateDonePayload | null;
  probe: ProbePayload | null;
};

export type RowTone = "neutral" | "pass" | "block" | "amber";

export type TimelineRow = {
  key: string;
  author: string;
  ts: number;
  line: string;
  tone: RowTone;
  raw: string;
  verdict?: VerdictPayload;
  escalation?: EscalationPayload;
};

export type RunPhase = "idle" | "running" | "settled" | "lost";

export type RunState = {
  phase: RunPhase;
  target: string | null;
  step: string | null;
  rows: TimelineRow[];
  gates: Record<GateName, GateCardState>;
  verdict: VerdictPayload | null;
  escalation: EscalationPayload | null;
  verdictStatus: ChipStatus;
  escalationStatus: ChipStatus;
  failure: string | null;
  elapsedMs: number | null;
  startedAt: number | null;
};

function freshGates(): Record<GateName, GateCardState> {
  return GATE_ORDER.reduce(
    (acc, gate) => {
      acc[gate] = {
        gate,
        status: "PENDING",
        sourceOfTruth: GATE_SOURCE_OF_TRUTH[gate],
        done: null,
        probe: null,
      };
      return acc;
    },
    {} as Record<GateName, GateCardState>,
  );
}

export const IDLE_STATE: RunState = {
  phase: "idle",
  target: null,
  step: null,
  rows: [],
  gates: freshGates(),
  verdict: null,
  escalation: null,
  verdictStatus: "PENDING",
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
  if (payload.incident_id) {
    return `Incident ${payload.incident_id} opened${payload.incident_title ? `: ${payload.incident_title}` : ""}`;
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

export type RunHandle = {
  state: RunState;
  start: (asset: string) => void;
  retry: () => void;
  busy: boolean;
};

export function useRun(): RunHandle {
  const [state, setState] = useState<RunState>(IDLE_STATE);
  const abortRef = useRef<AbortController | null>(null);
  const lastTarget = useRef<string | null>(null);
  const counter = useRef(0);

  const start = useCallback((asset: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    lastTarget.current = asset;
    counter.current = 0;
    const startedAt = Date.now();

    setState({
      ...IDLE_STATE,
      gates: freshGates(),
      phase: "running",
      target: asset,
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
        let escalation = prev.escalation;
        let verdictStatus = prev.verdictStatus;
        let escalationStatus = prev.escalationStatus;
        let elapsedMs = prev.elapsedMs;

        if (parsed.kind === "gate-running") {
          const gate = parsed.gate;
          gates[gate] = {
            ...gates[gate],
            status: "RUNNING",
            sourceOfTruth: GATE_SOURCE_OF_TRUTH[gate],
          };
          step = GATE_STEP[gate];
          rows = [
            ...rows,
            {
              key,
              author,
              ts,
              line: `Started. ${GATE_STEP[gate]}`,
              tone: "neutral",
              raw: pretty(text),
            },
          ];
        } else if (parsed.kind === "gate-done") {
          const gate = parsed.gate;
          gates[gate] = { ...gates[gate], status: parsed.payload.status, done: parsed.payload };
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
            },
          ];
        } else if (parsed.kind === "probe") {
          const gate = parsed.payload.gate;
          gates[gate] = { ...gates[gate], probe: parsed.payload };
          verdictStatus = "RUNNING";
          step = `Asking Grafana about ${gate}`;
          rows = [
            ...rows,
            {
              key,
              author,
              ts,
              line: `${gate}: ${parsed.payload.health}${parsed.payload.calibrated ? "" : ", never calibrated"}`,
              tone: parsed.payload.calibrated && /healthy/i.test(parsed.payload.health) ? "neutral" : "amber",
              raw: pretty(text),
            },
          ];
        } else if (parsed.kind === "verdict") {
          verdict = parsed.payload;
          verdictStatus = parsed.payload.status;
          elapsedMs = parsed.payload.elapsed_ms ?? elapsedMs;
          escalationStatus = "RUNNING";
          step = parsed.payload.needs_human
            ? "Escalation agent opening an incident"
            : "Writing the verdict annotation to Grafana";
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
        } else if (parsed.kind === "escalation") {
          escalation = parsed.payload;
          escalationStatus = parsed.payload.opened || parsed.payload.fallback ? "BLOCK" : "PASS";
          step = null;
          rows = [
            ...rows,
            {
              key,
              author,
              ts,
              line: escalationLine(parsed.payload),
              tone: parsed.payload.opened || parsed.payload.fallback ? "block" : "neutral",
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
          escalation,
          verdictStatus,
          escalationStatus,
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
          body: JSON.stringify({ asset }),
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
                elapsedMs: prev.elapsedMs ?? elapsed,
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

  const retry = useCallback(() => {
    if (lastTarget.current) start(lastTarget.current);
  }, [start]);

  return { state, start, retry, busy: state.phase === "running" };
}
