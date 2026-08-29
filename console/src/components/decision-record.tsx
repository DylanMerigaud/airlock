"use client";

import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { groupRuleIds, readC2pa } from "@/lib/events";
import type { RunState } from "@/lib/use-run";

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 12 12"
      width="11"
      height="11"
      aria-hidden="true"
      className={cn("shrink-0 text-ink-soft transition-transform duration-150", open && "rotate-90")}
    >
      <path d="M4 2.5 8 6l-4 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

/**
 * The paperwork the run leaves behind: the rules it cited, what C2PA said, the
 * annotation and incident it wrote, and the one action a reviewer can take.
 */
export function DecisionRecord({
  state,
  dashboardUrl,
  reviewed,
  onMarkReviewed,
}: {
  state: RunState;
  dashboardUrl: string;
  reviewed: boolean;
  onMarkReviewed: () => void;
}) {
  const [rulesOpen, setRulesOpen] = React.useState(false);
  const verdict = state.verdict;

  if (!verdict) {
    return (
      <p className="px-3 py-4 text-[13px] leading-[1.5] text-ink-soft">
        Nothing recorded yet. A finished run writes its rules, its C2PA reading, its Grafana
        annotation and any incident here.
      </p>
    );
  }

  const ruleIds = Array.from(
    new Set([
      ...(verdict.rule_ids ?? []),
      ...(verdict.gates ?? [])
        .filter((g) => (verdict.status === "PASS" ? true : g.status !== "PASS"))
        .flatMap((g) => g.rule_ids ?? []),
    ]),
  );
  const groups = groupRuleIds(ruleIds);
  const c2pa = readC2pa(state.gates.provenance.done);
  const escalation = state.escalation;

  return (
    <div>
      <section className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-3 py-2">
        <h3 className="label-micro text-ink-soft">Written to Grafana during the run</h3>
        <span className="font-mono text-[10.5px] text-ink-soft">
          {verdict.annotation_id !== undefined && verdict.annotation_id !== null
            ? `annotation ${verdict.annotation_id}`
            : "no annotation id"}
          {escalation?.incident_id ? `, incident ${escalation.incident_id}` : ""}
        </span>
      </section>

      {ruleIds.length > 0 && (
        <section className="border-b border-line px-3 py-2">
          <button
            type="button"
            onClick={() => setRulesOpen((value) => !value)}
            aria-expanded={rulesOpen}
            aria-controls="rules-cited"
            className="label-micro flex w-full items-center justify-between gap-2 text-ink-soft transition-colors hover:text-ink"
          >
            Rules cited ({ruleIds.length})
            <Chevron open={rulesOpen} />
          </button>
          {rulesOpen && (
            <div id="rules-cited" className="fade-in mt-2.5 space-y-2">
              {groups.map((group) => (
                <div key={group.source}>
                  <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-soft">
                    {group.source}
                  </p>
                  <ul className="mt-1.5 flex flex-wrap gap-1.5">
                    {group.ids.map((id) => (
                      <li key={id}>
                        <Badge tone="ink" size="xs" className="normal-case tracking-[0.01em]">
                          {id}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {c2pa && (
        <section className="border-b border-line px-3 py-2">
          <h3 className="label-micro text-ink-soft">Provenance</h3>
          <p
            className={cn(
              "mt-1 font-mono text-[11px] leading-[1.5]",
              c2pa.ok ? "text-ink" : "text-block",
            )}
          >
            {c2pa.line}
          </p>
        </section>
      )}

      <section className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2">
        <span className="text-[12.5px] leading-[1.45] text-ink-soft">
          The verdict agent wrote the annotation itself.
        </span>
        <a
          href={dashboardUrl}
          target="_blank"
          rel="noreferrer"
          className="text-[12.5px] text-accent underline underline-offset-[3px]"
        >
          Open in Grafana
        </a>
      </section>

      {verdict.needs_human && (
        <section className="px-3 py-2.5">
          {reviewed ? (
            <>
              <p className="flex items-center gap-2 text-[13px] text-ink">
                <span className="h-[8px] w-[8px] rounded-[1px] bg-pass" aria-hidden="true" />
                Reviewed by a human.
              </p>
              <p className="mt-1 text-[12px] leading-[1.45] text-ink-soft">
                Recorded in this browser only. In production this closes the incident and writes
                the reviewer back to the annotation.
              </p>
            </>
          ) : (
            <>
              <Button variant="outline" size="sm" onClick={onMarkReviewed} className="w-full">
                Mark reviewed by a human
              </Button>
              <p className="mt-1.5 text-[12px] leading-[1.45] text-ink-soft">
                In production this closes the incident. Here it only marks the record.
              </p>
            </>
          )}
        </section>
      )}
    </div>
  );
}
