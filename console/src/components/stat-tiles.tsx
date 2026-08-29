"use client";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export type StatsView = {
  ok: boolean;
  mock: boolean;
  checked_7d: number | null;
  passed_7d: number | null;
  blocked_7d: number | null;
  incidents_7d: number | null;
  gates_calibrated: number | null;
  gates_total: number;
  error: string | null;
};

function Stat({
  label,
  value,
  suffix,
  unavailable,
  reason,
}: {
  label: string;
  value: number | null;
  suffix?: string;
  unavailable: boolean;
  reason: string | null;
}) {
  return (
    <div className="flex items-baseline gap-1.5 whitespace-nowrap">
      <span className="text-[12px] leading-none text-ink-soft">{label}</span>
      {unavailable || value === null ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-help font-mono text-[11px] uppercase leading-none text-block">
              unavailable
            </span>
          </TooltipTrigger>
          <TooltipContent>{reason ?? "Grafana returned no sample for this query."}</TooltipContent>
        </Tooltip>
      ) : (
        <span className="tabular text-[14px] font-bold leading-none text-ink">
          {value}
          {suffix && <span className="ml-1 text-[11px] font-normal text-ink-soft">{suffix}</span>}
        </span>
      )}
    </div>
  );
}

/** The seven day ledger, inline: five numbers and where they came from. */
export function StatTiles({ stats, loading }: { stats: StatsView | null; loading: boolean }) {
  const unavailable = !loading && (!stats || !stats.ok);
  const reason = stats?.error ?? "The console could not reach the stats route.";

  return (
    <div
      aria-label="Seven day totals, read from Grafana"
      role="group"
      className="flex flex-wrap items-baseline gap-x-5 gap-y-1.5"
    >
      <Stat label="Checked" value={stats?.checked_7d ?? null} unavailable={unavailable} reason={reason} />
      <Stat label="Blocked" value={stats?.blocked_7d ?? null} unavailable={unavailable} reason={reason} />
      <Stat label="Passed" value={stats?.passed_7d ?? null} unavailable={unavailable} reason={reason} />
      <Stat
        label="Gates calibrated"
        value={stats?.gates_calibrated ?? null}
        suffix={`of ${stats?.gates_total ?? 4}`}
        unavailable={unavailable}
        reason={reason}
      />
      <Stat label="Incidents" value={stats?.incidents_7d ?? null} unavailable={unavailable} reason={reason} />
      <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-soft">
        last 7 days
      </span>
    </div>
  );
}
