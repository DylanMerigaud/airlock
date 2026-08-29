"use client";

import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader, PanelTitle } from "@/components/ui/card";
import { cn, offset } from "@/lib/utils";
import type { RowTone, RunState, TimelineRow } from "@/lib/use-run";

const AUTHOR_TONE: Record<RowTone, "neutral" | "pass" | "block" | "amber"> = {
  neutral: "neutral",
  pass: "pass",
  block: "block",
  amber: "amber",
};

const LINE_TONE: Record<RowTone, string> = {
  neutral: "text-ink-dim",
  pass: "text-ink",
  block: "text-block",
  amber: "text-amber",
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
    <li className="enter-row border-b border-line-soft last:border-b-0">
      <div className="grid grid-cols-[64px_minmax(0,1fr)] gap-3 px-4 py-3">
        <span className="tabular pt-[3px] font-mono text-[11px] text-ink-faint">
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
                tone="amber"
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

          <p className={cn("mt-1.5 text-[13px] leading-[1.5]", LINE_TONE[row.tone])}>{row.line}</p>

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
            <button
              type="button"
              onClick={onToggle}
              aria-expanded={open}
              aria-controls={panelId}
              className="label-micro inline-flex items-center gap-1.5 text-ink-faint transition-colors hover:text-ink-dim"
            >
              <ChevronGlyph open={open} />
              {open ? "Hide raw event" : "Raw event"}
            </button>

            {verdict && (
              <a
                href={dashboardUrl}
                target="_blank"
                rel="noreferrer"
                className="label-micro inline-flex items-center gap-1.5 text-amber underline decoration-amber/40 underline-offset-[3px] transition-colors hover:decoration-amber"
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
                className="label-micro inline-flex items-center gap-1.5 text-amber underline decoration-amber/40 underline-offset-[3px] transition-colors hover:decoration-amber"
              >
                Open the incident
              </a>
            )}
          </div>

          {open && (
            <pre
              id={panelId}
              className="mt-2.5 max-h-[280px] overflow-auto rounded-[3px] border border-line-soft bg-void px-3 py-2.5 font-mono text-[11px] leading-[1.6] text-ink-dim"
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
    <Panel className="flex min-h-[520px] flex-col">
      <PanelHeader>
        <PanelTitle>Event timeline</PanelTitle>
        <span className="tabular font-mono text-[10.5px] text-ink-faint">
          {state.rows.length} event{state.rows.length === 1 ? "" : "s"}
        </span>
      </PanelHeader>

      {state.phase === "lost" && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-block-deep/35 bg-block-shade px-4 py-3">
          <p className="text-[12.5px] leading-[1.5] text-block">
            {state.failure ?? "The event stream was lost."}
          </p>
          <Button variant="danger" size="sm" onClick={onRetry}>
            Retry the run
          </Button>
        </div>
      )}

      {state.rows.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-8 py-16 text-center">
          <p className="max-w-[42ch] text-[13px] leading-[1.6] text-ink-faint">
            {state.phase === "running"
              ? "Waiting for the first gate to report."
              : "No events yet. Run the airlock on an asset and every gate reports here, in the order it finished."}
          </p>
        </div>
      ) : (
        <ol className="flex-1">
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
        <div className="flex items-center gap-2.5 border-t border-line-soft bg-hull px-4 py-3">
          <span className="h-[6px] w-[6px] shrink-0 rotate-45 bg-amber lamp-live" aria-hidden="true" />
          <p aria-live="polite" className="font-mono text-[11.5px] text-amber">
            {state.step}
          </p>
        </div>
      )}
    </Panel>
  );
}
