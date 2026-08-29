"use client";

import * as React from "react";
import { StatusChip } from "@/components/status-chip";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, percent, shortSeconds } from "@/lib/utils";
import { GATE_ORDER, type ChipStatus, type GateName } from "@/lib/events";
import type { GateCardState } from "@/lib/use-run";

export type GateHealthView = {
  gate: GateName;
  state: "healthy" | "degraded" | "uncalibrated";
  error_rate_15m: number | null;
  seconds_since_success: number | null;
  calibration_catches_7d: number | null;
  exprs: Record<string, string>;
};

export type HealthView = {
  ok: boolean;
  mock: boolean;
  gates: GateHealthView[];
  error: string | null;
};

type Calibration = {
  text: string;
  tone: "quiet" | "amber" | "block";
  detail: string;
};

export function calibrationFor(
  health: HealthView | null,
  loading: boolean,
  gate: GateName,
): Calibration {
  if (loading) {
    return { text: "reading Grafana", tone: "quiet", detail: "The console is querying the Grafana datasource." };
  }
  if (!health || !health.ok) {
    return {
      text: "calibration unavailable",
      tone: "block",
      detail: health?.error ?? "The console could not reach Grafana.",
    };
  }
  const entry = health.gates.find((g) => g.gate === gate);
  if (!entry) {
    return {
      text: "calibration unavailable",
      tone: "block",
      detail: "Grafana returned no series for this gate.",
    };
  }

  const detail = [
    `error_rate_15m ${entry.error_rate_15m === null ? "no sample" : entry.error_rate_15m.toFixed(2)}`,
    `seconds_since_success ${entry.seconds_since_success === null ? "no sample" : entry.seconds_since_success.toFixed(1)}`,
    `calibration_catches_7d ${entry.calibration_catches_7d === null ? "no sample" : entry.calibration_catches_7d}`,
  ].join("\n");

  if (entry.state === "degraded") {
    if (entry.error_rate_15m !== null && entry.error_rate_15m > 0) {
      return { text: `degraded: error rate ${percent(entry.error_rate_15m)}`, tone: "amber", detail };
    }
    if (entry.seconds_since_success === null) {
      return { text: "degraded: no success in the last 7d", tone: "amber", detail };
    }
    return {
      text: `degraded: last success ${shortSeconds(entry.seconds_since_success)} ago`,
      tone: "amber",
      detail,
    };
  }

  if (entry.state === "uncalibrated") {
    return { text: "never calibrated: ADVISORY", tone: "amber", detail };
  }

  const catches = entry.calibration_catches_7d ?? 0;
  return {
    text: `caught ${catches} injected defect${catches === 1 ? "" : "s"} in 7d, last success ${shortSeconds(entry.seconds_since_success)} ago`,
    tone: "quiet",
    detail,
  };
}

function Rail({
  live,
  settled,
  first,
  last,
}: {
  live: boolean;
  settled: boolean;
  first: boolean;
  last: boolean;
}) {
  return (
    <div className="relative" aria-hidden="true">
      {!first && (
        <span className="absolute left-1/2 top-[-12px] h-[30px] w-px -translate-x-1/2 bg-line" />
      )}
      {!last && (
        <span
          className={cn(
            "absolute bottom-[-12px] left-1/2 top-[18px] w-px -translate-x-1/2",
            live ? "rail-live" : settled ? "bg-[#39404b]" : "bg-line",
          )}
        />
      )}
      <span
        className={cn(
          "absolute left-1/2 top-[18px] h-[7px] w-[7px] -translate-x-1/2 -translate-y-1/2 rotate-45 border",
          live
            ? "border-amber bg-amber"
            : settled
              ? "border-[#4b5460] bg-[#39404b]"
              : "border-line bg-hull",
        )}
      />
    </div>
  );
}

function CardShell({
  index,
  total,
  status,
  children,
}: {
  index: number;
  total: number;
  status: ChipStatus;
  children: React.ReactNode;
}) {
  const live = status === "RUNNING";
  const settled = status === "PASS" || status === "BLOCK" || status === "ERROR";
  return (
    <li className="grid grid-cols-[16px_minmax(0,1fr)] gap-3">
      <Rail live={live} settled={settled} first={index === 0} last={index === total - 1} />
      {children}
    </li>
  );
}

const TONE_CLASS: Record<Calibration["tone"], string> = {
  quiet: "text-ink-faint",
  amber: "text-amber",
  block: "text-block",
};

function GateCard({
  index,
  total,
  card,
  health,
  loading,
}: {
  index: number;
  total: number;
  card: GateCardState;
  health: HealthView | null;
  loading: boolean;
}) {
  const calibration = calibrationFor(health, loading, card.gate);
  const live = card.status === "RUNNING";
  const bad = card.status === "BLOCK" || card.status === "ERROR";

  return (
    <CardShell index={index} total={total} status={card.status}>
      <article
        className={cn(
          "relative overflow-hidden rounded-[4px] border bg-panel px-3.5 py-3 transition-colors",
          live && "scanning border-amber/40",
          !live && bad && "border-block-deep/40",
          !live && !bad && "border-line",
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-mono text-[12px] uppercase tracking-[0.16em] text-ink">
            {card.gate}
          </h3>
          <StatusChip status={card.status} />
        </div>
        <p className="mt-2 text-[12px] leading-[1.45] text-ink-dim">{card.sourceOfTruth}</p>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              className={cn(
                "mt-2.5 flex w-full items-start gap-1.5 border-t border-line-soft pt-2.5 text-left",
                "font-mono text-[10.5px] leading-[1.5] tracking-[0.02em]",
                TONE_CLASS[calibration.tone],
              )}
            >
              <span className="mt-[3px] h-[6px] w-[6px] shrink-0 rotate-45 border border-current" aria-hidden="true" />
              <span>
                <span className="sr-only">Calibration, read from Grafana: </span>
                {calibration.text}
              </span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">
            <span className="whitespace-pre-line">{calibration.detail}</span>
          </TooltipContent>
        </Tooltip>
      </article>
    </CardShell>
  );
}

function VerdictGateCard({
  index,
  total,
  status,
  probed,
}: {
  index: number;
  total: number;
  status: ChipStatus;
  probed: number;
}) {
  const live = status === "RUNNING";
  const bad = status === "BLOCK" || status === "ERROR";
  return (
    <CardShell index={index} total={total} status={status}>
      <article
        className={cn(
          "relative overflow-hidden rounded-[4px] border bg-panel px-3.5 py-3 transition-colors",
          live && "scanning border-amber/40",
          !live && bad && "border-block-deep/40",
          !live && !bad && "border-line",
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-mono text-[12px] uppercase tracking-[0.16em] text-ink">verdict</h3>
          <StatusChip status={status} />
        </div>
        <p className="mt-2 text-[12px] leading-[1.45] text-ink-dim">
          Grafana: error rate, last success, calibration catches
        </p>
        <p className="mt-2.5 border-t border-line-soft pt-2.5 font-mono text-[10.5px] leading-[1.5] text-ink-faint">
          {probed} of 4 gates probed through mcp-grafana
        </p>
      </article>
    </CardShell>
  );
}

function EscalationRow({
  index,
  total,
  status,
  line,
}: {
  index: number;
  total: number;
  status: ChipStatus;
  line: string;
}) {
  return (
    <CardShell index={index} total={total} status={status}>
      <div className="flex items-center justify-between gap-3 rounded-[4px] border border-line-soft bg-hull px-3.5 py-2.5">
        <div className="min-w-0">
          <h3 className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-dim">
            escalation
          </h3>
          <p className="mt-1 line-clamp-2 text-[11.5px] leading-[1.4] text-ink-faint">{line}</p>
        </div>
        <StatusChip status={status} />
      </div>
    </CardShell>
  );
}

export function GateColumn({
  gates,
  verdictStatus,
  escalationStatus,
  escalationLine,
  health,
  loading,
}: {
  gates: Record<GateName, GateCardState>;
  verdictStatus: ChipStatus;
  escalationStatus: ChipStatus;
  escalationLine: string;
  health: HealthView | null;
  loading: boolean;
}) {
  const probed = GATE_ORDER.filter((g) => gates[g].probe !== null).length;
  const total = 6;
  return (
    <ol className="space-y-3">
      {GATE_ORDER.map((gate, i) => (
        <GateCard
          key={gate}
          index={i}
          total={total}
          card={gates[gate]}
          health={health}
          loading={loading}
        />
      ))}
      <VerdictGateCard index={4} total={total} status={verdictStatus} probed={probed} />
      <EscalationRow index={5} total={total} status={escalationStatus} line={escalationLine} />
    </ol>
  );
}
