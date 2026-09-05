"use client";

import * as React from "react";
import { FindingText } from "@/components/finding-text";
import { cn } from "@/lib/utils";
import { stamp } from "@/lib/timecodes";
import { GATE_DOT } from "@/lib/instrument";
import type { Finding } from "@/lib/findings";
import type { RunPhase } from "@/lib/use-run";

const Row = React.forwardRef<
  HTMLLIElement,
  {
    finding: Finding;
    active: boolean;
    onSeek: (seconds: number) => void;
    onHover: (seconds: number | null) => void;
  }
>(function Row({ finding, active, onSeek, onHover }, ref) {
  const item = finding.item;
  // "consumer testimonial, spoken, 7s to 10s": what the record says about itself, one mono line.
  const meta = item
    ? [
        item.kind,
        item.channel,
        finding.seconds !== null && item.endSeconds !== null && item.endSeconds > finding.seconds
          ? `${stamp(finding.seconds)} to ${stamp(item.endSeconds)}`
          : null,
      ]
        .filter((part): part is string => Boolean(part))
        .join(", ")
    : null;
  return (
    <li
      ref={ref}
      className={cn(
        "border-b border-line border-l-2 px-3 py-2 last:border-b-0",
        active ? "border-l-accent bg-accent-wash" : "border-l-transparent",
      )}
      onMouseEnter={() => onHover(finding.seconds)}
      onMouseLeave={() => onHover(null)}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="inline-flex items-center gap-1.5">
          <span className={cn("h-[9px] w-[3px]", GATE_DOT[finding.gate])} aria-hidden="true" />
          <span className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink">
            {finding.gate}
          </span>
        </span>
        {finding.seconds === null ? (
          <span className="font-mono text-[10px] uppercase tracking-[0.07em] text-ink-soft">
            whole clip
          </span>
        ) : (
          <button
            type="button"
            onClick={() => onSeek(finding.seconds as number)}
            onFocus={() => onHover(finding.seconds)}
            onBlur={() => onHover(null)}
            className="tabular rounded-[2px] border border-line-strong bg-surface px-1.5 py-[2px] font-mono text-[10px] text-ink transition-colors hover:bg-accent-wash hover:text-accent"
          >
            <span className="sr-only">Play the clip from </span>
            {stamp(finding.seconds)}
          </button>
        )}
        <span
          className={cn(
            "font-mono text-[10px] uppercase tracking-[0.08em]",
            finding.status === "PASS" ? "text-ink" : "text-block",
          )}
        >
          {finding.status}
        </span>
      </div>
      <p className="mt-1 text-[13px] leading-[1.45] text-ink">
        <FindingText text={finding.text} onSeek={onSeek} />
      </p>
      {meta && <p className="mt-1 font-mono text-[10.5px] leading-[1.4] text-ink-soft">{meta}</p>}
      {item?.why && <p className="mt-0.5 text-[12px] leading-[1.45] text-ink-soft">{item.why}</p>}
      {item && item.rules.length > 0 && (
        <p className="mt-0.5 font-mono text-[10.5px] leading-[1.4] text-ink-soft">{item.rules.join(", ")}</p>
      )}
    </li>
  );
});

/**
 * Every row the gates produced, oldest gate first, each one anchored to the
 * second of the clip it was read at: one row per claim, per brand sighting, per
 * exclusion hit when the gate's evidence carries them, one per sentence
 * otherwise. The region scrolls; the clip never moves.
 */
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
  const rows = React.useRef(new Map<string, HTMLLIElement>());

  // An issue is what a gate blocked or failed on; a PASS row is an attestation
  // (a passing gate's sentence, or a claim a gate read and let through), listed
  // below the issues under its own label so a clean run does not read as four
  // findings.
  const issues = findings.filter((finding) => finding.status !== "PASS");
  const attestations = findings.filter((finding) => finding.status === "PASS");

  // Clicking a marker on the scrubber has to land on the finding it belongs to.
  React.useEffect(() => {
    if (activeSecond === null) return;
    const finding = findings.find((item) => item.seconds === activeSecond);
    if (!finding) return;
    rows.current.get(finding.key)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeSecond, findings]);

  const renderRow = (finding: Finding) => (
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
  );

  return (
    <div>
      {findings.length === 0 ? (
        <p className="px-3 py-4 text-[13px] leading-[1.5] text-ink-soft">
          {phase === "running"
            ? (step ?? "Waiting for the first gate to report.")
            : "Nothing yet. Run the airlock and each gate writes what it read here, one row per claim or sighting, anchored to the second of the clip it read it at."}
        </p>
      ) : (
        <>
          {issues.length > 0 && <ol>{issues.map(renderRow)}</ol>}
          {attestations.length > 0 && (
            <section
              aria-label="Attestations"
              className={cn(issues.length > 0 && "border-t border-line")}
            >
              <h3 className="label-micro px-3 pb-1 pt-2.5 text-ink-soft">
                attestations
                <span className="ml-1.5 normal-case tracking-normal">
                  {issues.length === 0
                    ? "no issue found, what each gate read"
                    : "what the gates read and let through"}
                </span>
              </h3>
              <ol>{attestations.map(renderRow)}</ol>
            </section>
          )}
        </>
      )}

      {notes.length > 0 && (
        <section className="border-t border-line bg-sunk px-3 py-2.5">
          <h3 className="label-micro text-ink-soft">What the verdict added</h3>
          <ul className="mt-1.5 space-y-1.5">
            {notes.map((note) => (
              <li key={note} className="flex gap-2 text-[12.5px] leading-[1.45] text-ink">
                <span
                  className="mt-[7px] h-[3px] w-[3px] shrink-0 bg-ink-soft"
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
    </div>
  );
}
