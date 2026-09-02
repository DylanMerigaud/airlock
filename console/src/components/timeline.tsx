"use client";

import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn, offset } from "@/lib/utils";
import type { RowTone, RunState, TimelineRow } from "@/lib/use-run";

const AUTHOR_TONE: Record<RowTone, "neutral" | "pass" | "block" | "amber"> = {
  neutral: "neutral",
  pass: "pass",
  block: "block",
  amber: "amber",
};

const LINE_TONE: Record<RowTone, string> = {
  neutral: "text-ink",
  pass: "text-ink",
  block: "text-block",
  amber: "text-warn",
};

function ChevronGlyph({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 12 12"
      width="10"
      height="10"
      aria-hidden="true"
      className={cn("transition-transform duration-150", open && "rotate-90")}
    >
      <path d="M4 2.5 8 6l-4 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

function Row({
  row,
  dashboardUrl,
  open,
  onToggle,
}: {
  row: TimelineRow;
  dashboardUrl: string;
  open: boolean;
  onToggle: () => void;
}) {
  const panelId = `raw-${row.key}`;
  const verdict = row.verdict;
  const escalation = row.escalation;

  return (
    <li className="border-b border-line last:border-b-0">
      <div className="grid grid-cols-[58px_minmax(0,1fr)] gap-3 px-3 py-2">
        <span className="tabular pt-[2px] font-mono text-[11px] text-ink-soft">
          <span className="sr-only">at </span>
          {offset(row.ts)}
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={AUTHOR_TONE[row.tone]} size="xs">
              {row.author}
            </Badge>
            {row.muted && (
              <Badge
                tone="neutral"
                size="xs"
                title="This gate ran without pushing anything to Grafana."
              >
                muted
              </Badge>
            )}
            {verdict?.annotation_id !== undefined && verdict?.annotation_id !== null && (
              <Badge tone="quiet" size="xs">
                annotation {verdict.annotation_id}
              </Badge>
            )}
            {escalation?.incident_id && (
              <Badge tone="block" size="xs">
                incident {escalation.incident_id}
              </Badge>
            )}
            {escalation?.fallback_annotation_id !== undefined && (
              <Badge tone="amber" size="xs">
                needs-human annotation {escalation.fallback_annotation_id}
              </Badge>
            )}
          </div>

          <p className={cn("mt-1 text-[13px] leading-[1.45]", LINE_TONE[row.tone])}>{row.line}</p>

          <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1.5">
            <button
              type="button"
              onClick={onToggle}
              aria-expanded={open}
              aria-controls={panelId}
              className="inline-flex items-center gap-1.5 text-[12px] text-ink-soft transition-colors hover:text-ink"
            >
              <ChevronGlyph open={open} />
              {open ? "Hide raw event" : "Raw event"}
            </button>

            {verdict && (
              <a
                href={dashboardUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-[12px] text-accent underline underline-offset-[3px]"
              >
                Open in Grafana
                <svg viewBox="0 0 12 12" width="9" height="9" aria-hidden="true">
                  <path d="M4 2h6v6" fill="none" stroke="currentColor" strokeWidth="1.4" />
                  <path d="M10 2 4.5 7.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
                  <path d="M8.5 10H2V3.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
                </svg>
              </a>
            )}

            {escalation?.incident_url && (
              <a
                href={escalation.incident_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-[12px] text-accent underline underline-offset-[3px]"
              >
                Open the incident
              </a>
            )}
          </div>

          {open && (
            <pre
              id={panelId}
              className="fade-in mt-2 max-h-[280px] overflow-auto rounded-[2px] border border-line bg-sunk px-2.5 py-2 font-mono text-[11px] leading-[1.55] text-ink-soft"
            >
              {row.raw}
            </pre>
          )}
        </div>
      </div>
    </li>
  );
}

export function Timeline({
  state,
  dashboardUrl,
  onRetry,
}: {
  state: RunState;
  dashboardUrl: string;
  onRetry: () => void;
}) {
  const [open, setOpen] = React.useState<Set<string>>(new Set());
  const toggle = (key: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div>
      {state.phase === "lost" && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-3 py-2">
          <p className="text-[12.5px] leading-[1.45] text-block">
            {state.failure ?? "The event stream was lost."}
          </p>
          <Button variant="danger" size="sm" onClick={onRetry}>
            Retry the run
          </Button>
        </div>
      )}

      {state.rows.length === 0 ? (
        <div className="px-6 py-12 text-center">
          <p className="mx-auto max-w-[52ch] text-[13px] leading-[1.55] text-ink-soft">
            {state.phase === "running"
              ? "Waiting for the first gate to report."
              : "No events yet. Run the airlock on an asset and every gate reports here, in the order it finished."}
          </p>
        </div>
      ) : (
        <ol>
          {state.rows.map((row) => (
            <Row
              key={row.key}
              row={row}
              dashboardUrl={dashboardUrl}
              open={open.has(row.key)}
              onToggle={() => toggle(row.key)}
            />
          ))}
        </ol>
      )}

      {state.phase === "running" && state.step && (
        <div className="flex items-center gap-2 border-t border-line bg-sunk px-3 py-2">
          <span className="h-[7px] w-[7px] shrink-0 rounded-[1px] bg-accent" aria-hidden="true" />
          <p aria-live="polite" className="font-mono text-[11.5px] text-accent">
            {state.step}
          </p>
        </div>
      )}
    </div>
  );
}
