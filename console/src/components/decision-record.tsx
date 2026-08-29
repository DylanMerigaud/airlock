"use client";

import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader, PanelTitle } from "@/components/ui/card";
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
  if (!verdict) return null;

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
    <Panel className="mt-3">
      <PanelHeader>
        <PanelTitle>Decision record</PanelTitle>
        <span className="font-mono text-[10.5px] text-ink-soft">
          {verdict.annotation_id !== undefined && verdict.annotation_id !== null
            ? `annotation ${verdict.annotation_id}`
            : "no annotation id"}
          {escalation?.incident_id ? `, incident ${escalation.incident_id}` : ""}
        </span>
      </PanelHeader>

      {ruleIds.length > 0 && (
        <section className="border-b border-line-soft px-4 py-3">
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
            <div id="rules-cited" className="mt-3 space-y-2.5">
              {groups.map((group) => (
                <div key={group.source}>
                  <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-soft">
                    {group.source}
                  </p>
                  <ul className="mt-1.5 flex flex-wrap gap-1.5">
                    {group.ids.map((id) => (
                      <li key={id}>
                        <Badge tone="ink" size="xs" className="normal-case tracking-[0.02em]">
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
        <section className="border-b border-line-soft px-4 py-3">
          <h3 className="label-micro text-ink-soft">Provenance</h3>
          <p
            className={cn(
              "mt-1.5 font-mono text-[11px] leading-[1.55]",
              c2pa.ok ? "text-pass" : "text-block",
            )}
          >
            {c2pa.line}
          </p>
        </section>
      )}

      <section className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
        <span className="font-mono text-[10.5px] leading-[1.5] text-ink-soft">
          Written to Grafana by the verdict agent during the run.
        </span>
        <a
          href={dashboardUrl}
          target="_blank"
          rel="noreferrer"
          className="label-micro text-ember underline decoration-ember-line underline-offset-[3px] transition-colors hover:decoration-ember"
        >
          Open in Grafana
        </a>
      </section>

      {verdict.needs_human && (
        <section className="border-t border-line-soft bg-card-sunk px-4 py-3.5">
          {reviewed ? (
            <>
              <p className="flex items-center gap-2 text-[13px] text-pass">
                <span className="h-[7px] w-[7px] rotate-45 bg-pass" aria-hidden="true" />
                Reviewed by a human.
              </p>
              <p className="mt-1.5 text-[11.5px] leading-[1.55] text-ink-soft">
                Recorded in this browser only. In production this closes the incident and writes
                the reviewer back to the annotation.
              </p>
            </>
          ) : (
            <>
              <Button variant="outline" size="sm" onClick={onMarkReviewed} className="w-full">
                Mark reviewed by a human
              </Button>
              <p className="mt-2 text-[11.5px] leading-[1.55] text-ink-soft">
                In production this closes the incident. Here it only marks the card.
              </p>
            </>
          )}
        </section>
      )}
    </Panel>
  );
}
