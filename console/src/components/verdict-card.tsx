"use client";

import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader, PanelTitle } from "@/components/ui/card";
import { cn, ms } from "@/lib/utils";
import {
  GATE_ORDER,
  MOTIVE_COPY,
  groupRuleIds,
  motiveTone,
  readC2pa,
  type GateName,
} from "@/lib/events";
import type { GateCardState, RunState } from "@/lib/use-run";

function Headline({ word, tone }: { word: string; tone: "pass" | "block" | "amber" }) {
  const colour =
    tone === "pass" ? "text-pass" : tone === "amber" ? "text-amber" : "text-block";
  return (
    <p className={cn("text-[38px] font-semibold leading-none tracking-[-0.03em]", colour)}>{word}</p>
  );
}

function RuleChips({ ids, heading }: { ids: string[]; heading: string }) {
  const groups = groupRuleIds(ids);
  if (groups.length === 0) return null;
  return (
    <section className="border-t border-line-soft px-4 py-3.5">
      <h4 className="label-micro text-ink-faint">{heading}</h4>
      <div className="mt-2.5 space-y-2.5">
        {groups.map((group) => (
          <div key={group.source}>
            <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint/80">
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
    </section>
  );
}

function C2paLine({ gates }: { gates: Record<GateName, GateCardState> }) {
  const reading = readC2pa(gates.provenance.done);
  if (!reading) return null;
  return (
    <section className="border-t border-line-soft px-4 py-3">
      <h4 className="label-micro text-ink-faint">Provenance</h4>
      <p
        className={cn(
          "mt-1.5 font-mono text-[11px] leading-[1.55]",
          reading.ok ? "text-pass" : "text-block",
        )}
      >
        {reading.line}
      </p>
    </section>
  );
}

function IdleBody() {
  return (
    <div className="px-4 py-5">
      <p className="text-[14px] leading-[1.55] text-ink">Pick an asset and run the airlock.</p>
      <p className="mt-2.5 text-[12.5px] leading-[1.6] text-ink-dim">
        Four gates read the asset against a named source of truth. The verdict agent then asks
        Grafana whether each gate is healthy and has already caught an injected defect. A gate that
        cannot prove that is not allowed to say PASS.
      </p>
    </div>
  );
}

function RunningBody({ state }: { state: RunState }) {
  const reported = GATE_ORDER.filter((g) => state.gates[g].done !== null).length;
  return (
    <div className="px-4 py-5">
      <p className="label-micro text-amber">Running</p>
      <p className="mt-2.5 flex items-start gap-2.5 text-[14px] leading-[1.5] text-ink">
        <span
          className="mt-[7px] h-[6px] w-[6px] shrink-0 rotate-45 bg-amber lamp-live"
          aria-hidden="true"
        />
        <span aria-live="polite">{state.step ?? "Working"}</span>
      </p>
      <p className="mt-3 font-mono text-[11px] text-ink-faint">
        {reported} of 4 gates have reported
      </p>
    </div>
  );
}

export function VerdictCard({
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
  const verdict = state.verdict;

  const failedButNoVerdict = state.phase === "lost" && !verdict;

  const topTone = verdict
    ? verdict.status === "PASS"
      ? "border-t-pass"
      : motiveTone(verdict.motive) === "degraded"
        ? "border-t-amber"
        : "border-t-block-deep"
    : failedButNoVerdict
      ? "border-t-block-deep"
      : state.phase === "running"
        ? "border-t-amber"
        : "border-t-line";

  const ruleIds = verdict
    ? Array.from(
        new Set([
          ...(verdict.rule_ids ?? []),
          ...(verdict.gates ?? [])
            .filter((g) => (verdict.status === "PASS" ? true : g.status !== "PASS"))
            .flatMap((g) => g.rule_ids ?? []),
        ]),
      )
    : [];

  return (
    <Panel className={cn("border-t-[3px]", topTone)}>
      <PanelHeader>
        <PanelTitle>Verdict</PanelTitle>
        {state.elapsedMs !== null && (
          <span className="tabular font-mono text-[10.5px] text-ink-faint">
            {ms(state.elapsedMs)}
          </span>
        )}
      </PanelHeader>

      {!verdict && state.phase === "idle" && <IdleBody />}
      {!verdict && state.phase === "running" && <RunningBody state={state} />}

      {failedButNoVerdict && (
        <div className="px-4 py-5">
          <Headline word="ERROR" tone="block" />
          <p className="mt-3 text-[13px] leading-[1.55] text-ink">
            The run did not produce a verdict, so nothing was cleared.
          </p>
          <p className="mt-2 font-mono text-[11px] leading-[1.6] text-block">{state.failure}</p>
        </div>
      )}

      {verdict && (
        <>
          <div className="px-4 py-5">
            <Headline
              word={verdict.status}
              tone={
                verdict.status === "PASS"
                  ? "pass"
                  : motiveTone(verdict.motive) === "degraded"
                    ? "amber"
                    : "block"
              }
            />

            {verdict.status === "PASS" ? (
              <p className="mt-3 text-[13.5px] leading-[1.55] text-ink">
                All gates PASS, healthy and calibrated.
              </p>
            ) : (
              <>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Badge
                    tone={motiveTone(verdict.motive) === "degraded" ? "amber" : "block"}
                    size="xs"
                    className="normal-case tracking-[0.06em]"
                  >
                    {verdict.motive ?? "unspecified motive"}
                  </Badge>
                  {verdict.needs_human && (
                    <Badge tone="amber" size="xs">
                      needs a human
                    </Badge>
                  )}
                </div>
                {verdict.motive && MOTIVE_COPY[verdict.motive] && (
                  <p className="mt-2.5 text-[13px] leading-[1.55] text-ink-dim">
                    {MOTIVE_COPY[verdict.motive]}
                  </p>
                )}
              </>
            )}
          </div>

          {(verdict.reasons?.length ?? 0) > 0 && (
            <section className="border-t border-line-soft px-4 py-3.5">
              <h4 className="label-micro text-ink-faint">
                {verdict.status === "PASS" ? "What the gates found" : "Why it is blocked"}
              </h4>
              <ul className="mt-2.5 space-y-2">
                {(verdict.reasons ?? []).map((reason, i) => (
                  <li key={i} className="flex gap-2.5 text-[12.5px] leading-[1.55] text-ink">
                    <span
                      className={cn(
                        "mt-[7px] h-[5px] w-[5px] shrink-0 rotate-45",
                        verdict.status === "PASS" ? "bg-pass" : "bg-block-deep",
                      )}
                      aria-hidden="true"
                    />
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <RuleChips
            ids={ruleIds}
            heading={verdict.status === "PASS" ? "Rules checked" : "Rules that decided this"}
          />

          <C2paLine gates={state.gates} />

          <section className="flex flex-wrap items-center justify-between gap-2 border-t border-line-soft px-4 py-3">
            <span className="font-mono text-[10.5px] text-ink-faint">
              {verdict.annotation_id !== undefined && verdict.annotation_id !== null
                ? `Grafana annotation ${verdict.annotation_id}`
                : "No annotation id returned"}
            </span>
            <a
              href={dashboardUrl}
              target="_blank"
              rel="noreferrer"
              className="label-micro text-amber underline decoration-amber/40 underline-offset-[3px] transition-colors hover:decoration-amber"
            >
              Open in Grafana
            </a>
          </section>

          {verdict.needs_human && (
            <section className="border-t border-line-soft bg-hull px-4 py-3.5">
              {reviewed ? (
                <>
                  <p className="flex items-center gap-2 text-[13px] text-pass">
                    <span className="h-[6px] w-[6px] rotate-45 bg-pass" aria-hidden="true" />
                    Reviewed by a human.
                  </p>
                  <p className="mt-1.5 text-[11.5px] leading-[1.55] text-ink-faint">
                    Recorded in this browser only. In production this closes the incident and writes
                    the reviewer back to the annotation.
                  </p>
                </>
              ) : (
                <>
                  <Button variant="outline" size="sm" onClick={onMarkReviewed} className="w-full">
                    Mark reviewed by a human
                  </Button>
                  <p className="mt-2 text-[11.5px] leading-[1.55] text-ink-faint">
                    In production this closes the incident. Here it only marks the card.
                  </p>
                </>
              )}
            </section>
          )}
        </>
      )}
    </Panel>
  );
}
