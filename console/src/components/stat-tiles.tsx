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

function Tile({
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
  accent?: "block" | "pass" | "amber";
}) {
  const body =
    unavailable || value === null ? (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-help font-mono text-[13px] uppercase tracking-[0.1em] text-block">
            unavailable
          </span>
        </TooltipTrigger>
        <TooltipContent>{reason ?? "Grafana returned no sample for this query."}</TooltipContent>
      </Tooltip>
    ) : (
      <span
        className={cn(
          "tabular text-[30px] font-semibold leading-none tracking-[-0.03em]",
          accent === "block" ? "text-block" : accent === "pass" ? "text-pass" : "text-ink",
        )}
      >
        {value}
        {suffix && <span className="ml-1 text-[15px] font-normal text-ink-faint">{suffix}</span>}
      </span>
    );

  return (
    <div className="border-l border-line px-4 py-3.5 first:border-l-0">
      <p className="label-micro text-ink-faint">{label}</p>
      <p className="mt-2.5 flex h-[30px] items-end">{body}</p>
    </div>
  );
}

export function StatTiles({ stats, loading }: { stats: StatsView | null; loading: boolean }) {
  const unavailable = !loading && (!stats || !stats.ok);
  const reason = stats?.error ?? "The console could not reach the stats route.";

  return (
    <section
      aria-label="Seven day totals, read from Grafana"
      className="grid grid-cols-2 rounded-[4px] border border-line bg-panel sm:grid-cols-3 lg:grid-cols-5"
    >
      <Tile
        label="Assets checked 7d"
        value={stats?.checked_7d ?? null}
        unavailable={unavailable}
        reason={reason}
      />
      <Tile
        label="Blocked 7d"
        value={stats?.blocked_7d ?? null}
        unavailable={unavailable}
        reason={reason}
        accent="block"
      />
      <Tile
        label="Passed 7d"
        value={stats?.passed_7d ?? null}
        unavailable={unavailable}
        reason={reason}
        accent="pass"
      />
      <Tile
        label="Gates calibrated"
        value={stats?.gates_calibrated ?? null}
        suffix={`of ${stats?.gates_total ?? 4}`}
        unavailable={unavailable}
        reason={reason}
      />
      <Tile
        label="Incidents opened 7d"
        value={stats?.incidents_7d ?? null}
        unavailable={unavailable}
        reason={reason}
      />
    </section>
  );
}
