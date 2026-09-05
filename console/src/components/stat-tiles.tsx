"use client";

import type { ReactNode } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Outage } from "@/lib/instrument";
import { formatUsd } from "@/lib/utils";

export type StatsView = {
  ok: boolean;
  mock: boolean;
  checked_7d: number | null;
  passed_7d: number | null;
  blocked_7d: number | null;
  incidents_7d: number | null;
  gates_calibrated: number | null;
  gates_total: number;
  cost_per_check_usd_7d: number | null;
  error: string | null;
};

/** A soft grey bar the width of the number it stands in for. No motion. */
function Placeholder({ width }: { width: string }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-[11px] translate-y-[1px] rounded-[2px] bg-sunk"
      style={{ width }}
    />
  );
}

function Stat({
  label,
  value,
  suffix,
  note,
  pending,
  unavailable,
  reason,
  render,
  width = "22px",
}: {
  label: string;
  value: number | null;
  suffix?: string;
  note?: string;
  /** No reading yet: draw a placeholder, never a red word. */
  pending: boolean;
  /** The retry budget is spent and there is still no reading. */
  unavailable: boolean;
  reason: string;
  render?: (value: number) => ReactNode;
  width?: string;
}) {
  return (
    <div className="flex items-baseline gap-1.5 whitespace-nowrap">
      <span className="text-[12px] leading-none text-ink-soft">{label}</span>
      {value !== null ? (
        <span className="tabular text-[14px] font-bold leading-none text-ink">
          {render ? render(value) : value}
          {suffix && <span className="ml-1 text-[11px] font-normal text-ink-soft">{suffix}</span>}
          {note && <span className="ml-1.5 font-mono text-[10px] font-normal text-ink-soft">{note}</span>}
        </span>
      ) : pending ? (
        <>
          <Placeholder width={width} />
          <span className="sr-only">{reason}</span>
        </>
      ) : unavailable ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-help font-mono text-[11px] uppercase leading-none text-block">
              unavailable
            </span>
          </TooltipTrigger>
          <TooltipContent>{reason}</TooltipContent>
        </Tooltip>
      ) : (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-help font-mono text-[11px] leading-none text-ink-soft">
              no sample
            </span>
          </TooltipTrigger>
          <TooltipContent>Grafana returned no sample for this query.</TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}

/**
 * The seven day ledger, inline: six numbers and where they came from. While
 * Grafana has not answered yet, or is waking, the numbers are grey bars and
 * one quiet line says why; "unavailable" only once the retry budget is spent.
 */
export function StatTiles({
  stats,
  loading,
  outage,
}: {
  stats: StatsView | null;
  loading: boolean;
  outage: Outage | null;
}) {
  const pending = stats === null && (loading || (outage !== null && !outage.exhausted));
  const unavailable = stats === null && !pending;
  const note = outage
    ? outage.exhausted
      ? `${outage.reason.replace(", retrying", "")}, retrying every minute`
      : outage.reason
    : null;
  const reason = outage
    ? outage.exhausted
      ? `${note}. ${outage.raw}`
      : outage.reason
    : loading
      ? "Reading Grafana."
      : "The console could not reach the stats route.";

  const common = { pending, unavailable, reason };

  return (
    <div
      aria-label="Seven day totals, read from Grafana"
      role="group"
      className="flex flex-wrap items-baseline gap-x-5 gap-y-1.5"
    >
      <Stat label="Checked" value={stats?.checked_7d ?? null} {...common} />
      <Stat label="Blocked" value={stats?.blocked_7d ?? null} {...common} />
      <Stat label="Passed" value={stats?.passed_7d ?? null} {...common} />
      <Stat
        label="Gates calibrated"
        value={stats?.gates_calibrated ?? null}
        suffix={`of ${stats?.gates_total ?? 4}`}
        width="34px"
        {...common}
      />
      {/* The counter is airlock_incident_total, one sample per escalation whether it opened a new
          incident or joined an open one: "escalations" is the honest word for that, not "incidents"
          (found live, 2026-09-05: it read 41 beside 26 actual incidents). */}
      <Stat label="Escalations" value={stats?.incidents_7d ?? null} {...common} />
      <Stat
        label="Cost"
        value={stats?.cost_per_check_usd_7d ?? null}
        render={formatUsd}
        note="avg per check, 7 d, list price"
        width="40px"
        {...common}
      />
      <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-soft">
        last 7 days
      </span>
      {outage && note && (
        <span
          role="status"
          className="font-mono text-[10px] text-ink-soft"
          title={outage.raw}
        >
          {stats ? `${note}, showing the last reading` : note}
        </span>
      )}
    </div>
  );
}
