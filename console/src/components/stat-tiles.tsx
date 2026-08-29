"use client";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

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
  accent,
}: {
  label: string;
  value: number | null;
  suffix?: string;
  unavailable: boolean;
  reason: string | null;
  accent?: "block" | "pass";
}) {
  return (
    <div className="flex items-baseline gap-2 whitespace-nowrap">
      <span className="label-micro text-ink-soft">{label}</span>
      {unavailable || value === null ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-help font-mono text-[11px] uppercase tracking-[0.1em] text-block">
              unavailable
            </span>
          </TooltipTrigger>
          <TooltipContent>{reason ?? "Grafana returned no sample for this query."}</TooltipContent>
        </Tooltip>
      ) : (
        <span
          className={cn(
            "tabular text-[17px] font-semibold leading-none",
            accent === "block" ? "text-block" : accent === "pass" ? "text-pass" : "text-ink",
          )}
        >
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
    <section
      aria-label="Seven day totals, read from Grafana"
      className="flex flex-wrap items-baseline gap-x-6 gap-y-3 border-t border-line py-3.5"
    >
      <Stat label="Checked" value={stats?.checked_7d ?? null} unavailable={unavailable} reason={reason} />
      <Stat
        label="Blocked"
        value={stats?.blocked_7d ?? null}
        unavailable={unavailable}
        reason={reason}
        accent="block"
      />
      <Stat
        label="Passed"
        value={stats?.passed_7d ?? null}
        unavailable={unavailable}
        reason={reason}
        accent="pass"
      />
      <Stat
        label="Gates calibrated"
        value={stats?.gates_calibrated ?? null}
        suffix={`of ${stats?.gates_total ?? 4}`}
        unavailable={unavailable}
        reason={reason}
      />
      <Stat
        label="Incidents"
        value={stats?.incidents_7d ?? null}
        unavailable={unavailable}
        reason={reason}
      />
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-soft">
        last 7 days
      </span>
    </section>
  );
}
