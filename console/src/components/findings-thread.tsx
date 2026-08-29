"use client";

import * as React from "react";
import { Panel, PanelHeader, PanelTitle } from "@/components/ui/card";
import { FindingText } from "@/components/finding-text";
import { cn } from "@/lib/utils";
import { stamp } from "@/lib/timecodes";
import { GATE_DOT } from "@/lib/instrument";
import type { Finding } from "@/lib/findings";
import type { RunPhase } from "@/lib/use-run";

const VISIBLE = 6;

const Row = React.forwardRef<
  HTMLLIElement,
  {
    finding: Finding;
    active: boolean;
    onSeek: (seconds: number) => void;
    onHover: (seconds: number | null) => void;
  }
>(function Row({ finding, active, onSeek, onHover }, ref) {
  return (
    <li
      ref={ref}
      className={cn(
        "enter-row border-l-2 px-4 py-3 transition-colors",
        active
          ? "border-l-ember bg-ember-wash"
          : finding.status === "PASS"
            ? "border-l-pass-line"
            : "border-l-block-line",
      )}
      onMouseEnter={() => onHover(finding.seconds)}
      onMouseLeave={() => onHover(null)}
    >
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <span className="inline-flex items-center gap-1.5">
          <span className={cn("h-[9px] w-[3px]", GATE_DOT[finding.gate])} aria-hidden="true" />
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink">
            {finding.gate}
          </span>
        </span>
        {finding.seconds === null ? (
          <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-soft">
            whole clip
          </span>
        ) : (
          <button
            type="button"
            onClick={() => onSeek(finding.seconds as number)}
            onFocus={() => onHover(finding.seconds)}
            onBlur={() => onHover(null)}
            className="tabular rounded-[2px] border border-line bg-card-sunk px-1.5 py-[2px] font-mono text-[10px] text-ink-mid transition-colors hover:border-ember hover:bg-ember hover:text-card"
          >
            <span className="sr-only">Play the clip from </span>
            {stamp(finding.seconds)}
          </button>
        )}
        <span
          className={cn(
            "font-mono text-[9.5px] uppercase tracking-[0.14em]",
            finding.status === "PASS" ? "text-pass" : "text-block",
          )}
        >
          {finding.status}
        </span>
      </div>
      <p className="mt-1.5 text-[12.5px] leading-[1.55] text-ink">
        <FindingText text={finding.text} onSeek={onSeek} />
      </p>
    </li>
  );
});

export function FindingsThread({
  findings,
  notes,
  phase,
  step,
  activeSecond,
  onSeek,
  onHover,
}: {
  findings: Finding[];
  notes: string[];
  phase: RunPhase;
  step: string | null;
  activeSecond: number | null;
  onSeek: (seconds: number) => void;
  onHover: (seconds: number | null) => void;
}) {
  const [expanded, setExpanded] = React.useState(false);
  const hidden = Math.max(0, findings.length - VISIBLE);
  const shown = expanded ? findings : findings.slice(hidden);
  const rows = React.useRef(new Map<string, HTMLLIElement>());

  // Clicking a marker on the scrubber has to land on the finding it belongs to,
  // even when that finding is one of the older ones folded away.
  React.useEffect(() => {
    if (activeSecond === null) return;
    const index = findings.findIndex((finding) => finding.seconds === activeSecond);
    if (index === -1) return;
    if (index < findings.length - VISIBLE) setExpanded(true);
    const node = rows.current.get(findings[index].key);
    node?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeSecond, findings]);

  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>Findings, oldest first</PanelTitle>
        <span className="tabular font-mono text-[10.5px] text-ink-soft">
          {findings.length} finding{findings.length === 1 ? "" : "s"}
        </span>
      </PanelHeader>

      {findings.length === 0 ? (
        <p className="px-4 py-6 text-[12.5px] leading-[1.6] text-ink-soft">
          {phase === "running"
            ? (step ?? "Waiting for the first gate to report.")
            : "Nothing yet. Run the airlock and each gate writes what it read here, anchored to the second of the clip it read it at."}
        </p>
      ) : (
        <>
          {hidden > 0 && !expanded && (
            <div className="border-b border-line-soft px-4 py-2">
              <button
                type="button"
                onClick={() => setExpanded(true)}
                className="label-micro text-ember underline decoration-ember-line underline-offset-[3px] hover:decoration-ember"
              >
                Show all {findings.length} findings
              </button>
            </div>
          )}
          <ol className="divide-y divide-line-soft">
            {shown.map((finding) => (
              <Row
                key={finding.key}
                ref={(node) => {
                  if (node) rows.current.set(finding.key, node);
                  else rows.current.delete(finding.key);
                }}
                finding={finding}
                active={finding.seconds !== null && finding.seconds === activeSecond}
                onSeek={onSeek}
                onHover={onHover}
              />
            ))}
          </ol>
        </>
      )}

      {notes.length > 0 && (
        <section className="border-t border-line-soft bg-card-sunk px-4 py-3">
          <h3 className="label-micro text-ink-soft">What the verdict added</h3>
          <ul className="mt-2 space-y-1.5">
            {notes.map((note) => (
              <li key={note} className="flex gap-2 text-[12px] leading-[1.55] text-ink-mid">
                <span
                  className="mt-[7px] h-[4px] w-[4px] shrink-0 rounded-full bg-ink-soft"
                  aria-hidden="true"
                />
                <span>
                  <FindingText text={note} onSeek={onSeek} />
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Panel>
  );
}
