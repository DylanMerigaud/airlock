"use client";

import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, ms } from "@/lib/utils";
import {
  GATE_ORDER,
  GATE_STEP,
  MOTIVE_COPY,
  motiveTone,
  type ChipStatus,
  type GateName,
} from "@/lib/events";
import { calibrationFor, GATE_DOT, type HealthView } from "@/lib/instrument";
import type { GateCardState, RunState } from "@/lib/use-run";

const MUTE_HELP =
  "The gate still runs but pushes nothing to Grafana. The verdict has to notice through Grafana that the control went dark.";

const TONE_CLASS = {
  quiet: "text-ink-soft",
  amber: "text-warn",
  block: "text-block",
} as const;

function CheckIcon({ status }: { status: ChipStatus }) {
  if (status === "PASS") {
    return (
      <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" className="text-pass">
        <circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" strokeWidth="1.4" />
        <path
          d="M4.8 8.3 6.9 10.4 11.2 5.9"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (status === "BLOCK") {
    return (
      <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" className="text-block">
        <path
          d="M8 1.6 15 14H1z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
        <path d="M8 6v3.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="8" cy="11.7" r="0.85" fill="currentColor" />
      </svg>
    );
  }
  if (status === "ERROR") {
    return (
      <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" className="text-block">
        <circle cx="8" cy="8" r="7" fill="currentColor" />
        <path
          d="M5.5 5.5 10.5 10.5M10.5 5.5 5.5 10.5"
          stroke="#fffdf8"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (status === "RUNNING") {
    return (
      <span className="flex h-4 w-4 items-center justify-center" aria-hidden="true">
        <span className="h-[9px] w-[9px] rounded-full bg-ember lamp-live" />
      </span>
    );
  }
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" className="text-ink-soft">
      <circle
        cx="8"
        cy="8"
        r="7"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeDasharray="2.6 2.6"
      />
    </svg>
  );
}

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

function CheckRow({
  name,
  hue,
  status,
  line,
  under,
  underTone = "quiet",
  badges,
  children,
}: {
  name: string;
  hue?: string;
  status: ChipStatus;
  line: string;
  under?: string;
  underTone?: keyof typeof TONE_CLASS;
  badges?: React.ReactNode;
  children?: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(false);
  const panelId = `check-${name}`;

  return (
    <li className={cn("border-b border-line-soft last:border-b-0", status === "RUNNING" && "scan-row")}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-card-sunk"
      >
        <span className="mt-[2px] shrink-0">
          <CheckIcon status={status} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {hue && <span className={cn("h-[9px] w-[3px]", hue)} aria-hidden="true" />}
            <span className="font-mono text-[11.5px] uppercase tracking-[0.14em] text-ink">
              {name}
            </span>
            {badges}
          </span>
          <span className="mt-1 block text-[12.5px] leading-[1.5] text-ink-mid">{line}</span>
          {under && (
            <span
              className={cn(
                "mt-1 block font-mono text-[10.5px] leading-[1.5]",
                TONE_CLASS[underTone],
              )}
            >
              {under}
            </span>
          )}
        </span>
        <Chevron open={open} />
      </button>
      {open && (
        <div id={panelId} className="border-t border-line-soft bg-card-sunk px-4 py-3.5">
          {children}
        </div>
      )}
    </li>
  );
}

function Evidence({ value }: { value: unknown }) {
  const text = React.useMemo(() => {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }, [value]);
  return (
    <pre className="mt-1.5 max-h-[240px] overflow-auto rounded-[3px] border border-line bg-card px-3 py-2.5 font-mono text-[11px] leading-[1.6] text-ink-mid">
      {text}
    </pre>
  );
}

function gateLine(card: GateCardState): string {
  if (card.status === "PENDING") return "Waiting to run";
  if (card.status === "RUNNING") return `Checking: ${GATE_STEP[card.gate].replace(": ", ", ")}`;
  const reasons = card.done?.reasons ?? [];
  const first = reasons[0] ?? `${card.gate} ${card.status}`;
  if (card.status === "PASS") return "No issues found";
  if (card.status === "ERROR") return `Check failed: ${first}`;
  return `${reasons.length || 1} issue${reasons.length === 1 ? "" : "s"} found: ${first}`;
}

export function ChecksPanel({
  state,
  health,
  healthLoading,
  mute,
  onToggleMute,
  muteDisabled,
  onRetry,
}: {
  state: RunState;
  health: HealthView | null;
  healthLoading: boolean;
  mute: GateName[];
  onToggleMute: (gate: GateName) => void;
  muteDisabled: boolean;
  onRetry: () => void;
}) {
  const verdict = state.verdict;
  const lostWithoutVerdict = state.phase === "lost" && !verdict;

  const word = verdict
    ? verdict.status
    : lostWithoutVerdict
      ? "ERROR"
      : state.phase === "running"
        ? "RUNNING"
        : "READY";

  const tone: "pass" | "block" | "warn" | "ember" | "quiet" = verdict
    ? verdict.status === "PASS"
      ? "pass"
      : motiveTone(verdict.motive) === "degraded"
        ? "warn"
        : "block"
    : lostWithoutVerdict
      ? "block"
      : state.phase === "running"
        ? "ember"
        : "quiet";

  const summary = verdict
    ? verdict.status === "PASS"
      ? "Checks complete: PASS, four gates healthy and calibrated."
      : `Checks complete: ${verdict.status}, ${verdict.motive ?? "unspecified motive"}${
          verdict.needs_human ? ", needs a human" : ""
        }.`
    : lostWithoutVerdict
      ? "The run did not produce a verdict, so nothing was cleared."
      : state.phase === "running"
        ? `Checks running. ${state.step ?? "Working"}.`
        : "Nothing checked yet. Pick a clip and press Run airlock.";

  const probed = GATE_ORDER.filter((g) => state.gates[g].probe !== null).length;
  const reported = GATE_ORDER.filter((g) => state.gates[g].done !== null).length;

  const escalation = state.escalation;

  return (
    <Panel
      className={cn(
        "border-t-[3px]",
        tone === "pass"
          ? "border-t-pass"
          : tone === "block"
            ? "border-t-block"
            : tone === "warn"
              ? "border-t-warn-mark"
              : tone === "ember"
                ? "border-t-ember"
                : "border-t-line",
      )}
    >
      <header className="px-4 pb-4 pt-3.5">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="label-micro text-ink-soft">Checks</h2>
          {state.elapsedMs !== null && (
            <span className="tabular font-mono text-[10.5px] text-ink-soft">
              {ms(state.elapsedMs)}
            </span>
          )}
        </div>

        <p
          className={cn(
            "display mt-1.5 text-[46px] font-semibold leading-none",
            tone === "pass"
              ? "text-pass"
              : tone === "block"
                ? "text-block"
                : tone === "warn"
                  ? "text-warn"
                  : tone === "ember"
                    ? "text-ember"
                    : "text-ink",
          )}
        >
          {word}
        </p>

        <p className="mt-3 text-[13.5px] leading-[1.5] text-ink" aria-live="polite">
          {summary}
        </p>

        {verdict && verdict.status !== "PASS" && (
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
        )}

        {verdict?.motive && MOTIVE_COPY[verdict.motive] && verdict.status !== "PASS" && (
          <p className="mt-2.5 text-[12.5px] leading-[1.55] text-ink-mid">
            {MOTIVE_COPY[verdict.motive]}
          </p>
        )}

        {state.phase === "running" && (
          <p className="mt-2.5 font-mono text-[11px] text-ink-soft">
            {reported} of 4 gates have reported
          </p>
        )}

        {state.phase === "lost" && (
          <div className="mt-3 rounded-[3px] border border-block-line bg-block-wash px-3 py-2.5">
            <p className="text-[12px] leading-[1.5] text-block">
              {state.failure ?? "The event stream closed before the run finished."}
            </p>
            <Button variant="danger" size="sm" className="mt-2.5" onClick={onRetry}>
              Retry the run
            </Button>
          </div>
        )}
      </header>

      <ol className="border-t border-line-soft">
        {GATE_ORDER.map((gate) => {
          const card = state.gates[gate];
          const calibration = calibrationFor(health, healthLoading, gate, card.reported);
          return (
            <CheckRow
              key={gate}
              name={gate}
              hue={GATE_DOT[gate]}
              status={card.status}
              line={gateLine(card)}
              under={calibration.text}
              underTone={calibration.tone}
              badges={
                card.muted ? (
                  <Badge tone="amber" size="xs" title={MUTE_HELP}>
                    muted
                  </Badge>
                ) : null
              }
            >
              <dl className="space-y-2.5 text-[12px] leading-[1.55]">
                <div>
                  <dt className="label-micro text-ink-soft">Source of truth</dt>
                  <dd className="mt-1 text-ink-mid">{card.sourceOfTruth}</dd>
                </div>
                <div>
                  <dt className="label-micro text-ink-soft">Calibration, read from Grafana</dt>
                  <dd className={cn("mt-1 font-mono text-[11px]", TONE_CLASS[calibration.tone])}>
                    {calibration.text}
                  </dd>
                  <dd className="mt-1 whitespace-pre-line font-mono text-[10.5px] text-ink-soft">
                    {calibration.detail}
                  </dd>
                </div>
                {card.done?.elapsed_ms !== undefined && (
                  <div>
                    <dt className="label-micro text-ink-soft">Ran in</dt>
                    <dd className="tabular mt-1 font-mono text-[11px] text-ink-mid">
                      {ms(card.done.elapsed_ms)}
                    </dd>
                  </div>
                )}
              </dl>

              <div className="mt-3 border-t border-line pt-3">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Switch
                      checked={mute.includes(gate)}
                      onCheckedChange={() => onToggleMute(gate)}
                      disabled={muteDisabled}
                      aria-describedby={`mute-help-${gate}`}
                    >
                      Mute telemetry
                    </Switch>
                  </TooltipTrigger>
                  <TooltipContent side="left">
                    <span className="block max-w-[34ch]">{MUTE_HELP}</span>
                  </TooltipContent>
                </Tooltip>
                <p
                  id={`mute-help-${gate}`}
                  className="mt-1.5 text-[11px] leading-[1.5] text-ink-soft"
                >
                  {MUTE_HELP}
                </p>
              </div>

              {card.done?.evidence !== undefined && (
                <div className="mt-3 border-t border-line pt-3">
                  <p className="label-micro text-ink-soft">Evidence</p>
                  <Evidence value={card.done.evidence} />
                </div>
              )}
            </CheckRow>
          );
        })}

        <CheckRow
          name="verdict"
          status={state.verdictStatus}
          line={
            state.verdictStatus === "PENDING"
              ? "Waiting for the gates to report"
              : state.verdictStatus === "RUNNING"
                ? (state.step ?? `Asking Grafana about every gate, ${probed} of 4 answered`)
                : verdict?.status === "PASS"
                  ? "No issues found: every gate healthy and calibrated"
                  : `Blocked: ${verdict?.motive ?? "no motive returned"}`
          }
          under={`${probed} of 4 gates probed through mcp-grafana`}
        >
          <dl className="space-y-2.5 text-[12px] leading-[1.55]">
            <div>
              <dt className="label-micro text-ink-soft">Source of truth</dt>
              <dd className="mt-1 text-ink-mid">
                Grafana: error rate, seconds since last success, calibration catches over 7 days
              </dd>
            </div>
            {GATE_ORDER.filter((gate) => state.gates[gate].probe).map((gate) => {
              const probe = state.gates[gate].probe;
              if (!probe) return null;
              return (
                <div key={gate}>
                  <dt className="label-micro text-ink-soft">{gate}</dt>
                  <dd className="mt-1 font-mono text-[11px] text-ink-mid">
                    {probe.health}
                    {probe.calibrated ? "" : ", never calibrated"}
                  </dd>
                </div>
              );
            })}
          </dl>
        </CheckRow>

        <CheckRow
          name="escalation"
          status={state.escalationStatus}
          line={
            escalation
              ? escalation.incident_id
                ? `Incident ${escalation.incident_id} opened${escalation.incident_title ? `: ${escalation.incident_title}` : ""}`
                : escalation.fallback_annotation_id !== undefined
                  ? `The Incident API refused, a needs-human annotation was written instead (id ${escalation.fallback_annotation_id})`
                  : (escalation.reason ?? "No escalation needed")
              : state.phase === "idle"
                ? "Opens an incident only when a human has to arbitrate"
                : "Waiting for the verdict"
          }
        >
          {escalation ? (
            <>
              {escalation.incident_url && (
                <a
                  href={escalation.incident_url}
                  target="_blank"
                  rel="noreferrer"
                  className="label-micro text-ember underline decoration-ember-line underline-offset-[3px] hover:decoration-ember"
                >
                  Open the incident
                </a>
              )}
              <p className="label-micro mt-3 text-ink-soft">What the escalation agent returned</p>
              <Evidence value={escalation} />
            </>
          ) : (
            <p className="text-[12px] leading-[1.55] text-ink-mid">
              An escalation is opened only when the verdict says a human has to arbitrate.
            </p>
          )}
        </CheckRow>
      </ol>

    </Panel>
  );
}
