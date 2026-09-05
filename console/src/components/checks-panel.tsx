"use client";

import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, duration } from "@/lib/utils";
import {
  formatGateUsage,
  GATE_INSTRUMENT,
  GATE_MEASURED,
  GATE_ORDER,
  GATE_STEP,
  MOTIVE_COPY,
  motiveTone,
  type ChipStatus,
  type FaultMap,
  type GateName,
} from "@/lib/events";
import { calibrationFor, GATE_DOT, type InstrumentReading } from "@/lib/instrument";
import type { GateCardState, RunState } from "@/lib/use-run";

/**
 * A once-a-second clock, only while something runs. It feeds the elapsed
 * counter on a running gate row: a number that changes, not an animation.
 */
function useNow(active: boolean): number {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}

function elapsedLine(card: GateCardState, now: number): string | null {
  if (card.status !== "RUNNING" || card.runningSince === null) return null;
  const seconds = Math.max(0, Math.round((now - card.runningSince) / 1000));
  const measured = GATE_MEASURED[card.gate];
  return `${GATE_INSTRUMENT[card.gate]}, ${seconds} s elapsed${measured ? `, ${measured}` : ""}`;
}

const MUTE_HELP =
  "The gate still runs but pushes nothing to Grafana. The verdict has to notice through Grafana that the control went dark.";

const FAULT_HELP =
  "The gate fails on purpose before it spends anything; the verdict must notice through Grafana.";

/** The gates a fault can be injected into from this panel: rights only for now. */
const FAULT_GATES: GateName[] = ["rights"];

const TONE_CLASS = {
  quiet: "text-ink-soft",
  amber: "text-warn",
  block: "text-block",
} as const;

/**
 * Status icons, all static. Green carries the pass mark but never a small
 * label: at 4.2:1 on white it clears the 3:1 an icon needs and not the 4.5:1
 * text needs, so every PASS word on this screen is set in ink beside it.
 */
function CheckIcon({ status }: { status: ChipStatus }) {
  if (status === "PASS") {
    return (
      <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" className="text-pass">
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
      <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" className="text-block">
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
      <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" className="text-block">
        <circle cx="8" cy="8" r="7" fill="currentColor" />
        <path
          d="M5.5 5.5 10.5 10.5M10.5 5.5 5.5 10.5"
          stroke="#ffffff"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (status === "RUNNING") {
    // Static: a ring three quarters closed. The step is said in words beside it.
    return (
      <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" className="text-accent">
        <circle
          cx="8"
          cy="8"
          r="7"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeDasharray="33 11"
          strokeLinecap="round"
        />
        <circle cx="8" cy="8" r="2.2" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" className="text-line-strong">
      <circle
        cx="8"
        cy="8"
        r="7"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
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
  underPending = false,
  counter,
  badges,
  children,
}: {
  name: string;
  hue?: string;
  status: ChipStatus;
  line: string;
  under?: string;
  underTone?: keyof typeof TONE_CLASS;
  /** The under line has no reading yet: draw a placeholder bar, keep the words for readers. */
  underPending?: boolean;
  /** The elapsed counter of a running gate. */
  counter?: string | null;
  badges?: React.ReactNode;
  children?: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(false);
  const panelId = `check-${name}`;

  return (
    <li className="border-b border-line last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-start gap-2.5 px-3 py-2 text-left transition-colors hover:bg-sunk"
      >
        <span className="mt-[1px] shrink-0">
          <CheckIcon status={status} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {hue && <span className={cn("h-[9px] w-[3px]", hue)} aria-hidden="true" />}
            <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-ink">
              {name}
            </span>
            {badges}
          </span>
          <span className="mt-0.5 block text-[13px] leading-[1.4] text-ink">{line}</span>
          {under && underPending && (
            <span className="mt-0.5 block font-mono text-[10.5px] leading-[1.4]">
              <span
                aria-hidden="true"
                className="inline-block h-[9px] w-[168px] translate-y-[1px] rounded-[2px] bg-sunk"
              />
              <span className="sr-only">{under}</span>
            </span>
          )}
          {under && !underPending && (
            <span
              className={cn(
                "mt-0.5 block font-mono text-[10.5px] leading-[1.4]",
                TONE_CLASS[underTone],
              )}
            >
              {under}
            </span>
          )}
          {counter && (
            <span className="tabular mt-0.5 block font-mono text-[10.5px] leading-[1.4] text-accent">
              {counter}
            </span>
          )}
        </span>
        <Chevron open={open} />
      </button>
      {open && (
        <div id={panelId} className="fade-in border-t border-line bg-sunk px-3 py-3">
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
    <pre className="mt-1.5 max-h-[220px] overflow-auto rounded-[2px] border border-line bg-surface px-2.5 py-2 font-mono text-[11px] leading-[1.55] text-ink-soft">
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

type Tone = "pass" | "block" | "warn" | "accent" | "quiet";

function verdictTone(state: RunState): Tone {
  const verdict = state.verdict;
  if (verdict) {
    if (verdict.status === "PASS") return "pass";
    return motiveTone(verdict.motive) === "degraded" ? "warn" : "block";
  }
  if (state.phase === "lost") return "block";
  if (state.phase === "running") return "accent";
  return "quiet";
}

/**
 * The verdict, above the segmented control, so it stays on screen whichever
 * segment the reviewer is reading. The word is the only large type on the page.
 */
export function VerdictSummary({
  state,
  onRetry,
}: {
  state: RunState;
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

  const tone = verdictTone(state);

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

  const reported = GATE_ORDER.filter((g) => state.gates[g].done !== null).length;

  return (
    <section
      aria-label="Verdict"
      className={cn(
        "rounded-[4px] border border-line bg-surface px-3 py-2.5",
        "border-t-[3px]",
        tone === "pass"
          ? "border-t-pass"
          : tone === "block"
            ? "border-t-block"
            : tone === "warn"
              ? "border-t-warn"
              : tone === "accent"
                ? "border-t-accent"
                : "border-t-line-strong",
      )}
    >
      <div className="flex items-baseline justify-between gap-3">
        <p
          className={cn(
            "text-[28px] font-bold leading-none tracking-[-0.01em]",
            tone === "pass"
              ? "text-pass"
              : tone === "block"
                ? "text-block"
                : tone === "warn"
                  ? "text-warn"
                  : tone === "accent"
                    ? "text-accent"
                    : "text-ink",
          )}
        >
          {word}
        </p>
        <div className="flex items-center gap-2">
          {verdict && verdict.status !== "PASS" && (
            <Badge
              tone={motiveTone(verdict.motive) === "degraded" ? "amber" : "block"}
              size="xs"
              className="normal-case tracking-[0.02em]"
            >
              {verdict.motive ?? "unspecified motive"}
            </Badge>
          )}
          {verdict?.needs_human && (
            <Badge tone="amber" size="xs" className="normal-case tracking-[0.02em]">
              needs a human
            </Badge>
          )}
          {state.elapsedMs !== null && (
            <span className="tabular font-mono text-[10.5px] text-ink-soft">
              {duration(state.elapsedMs)}
            </span>
          )}
        </div>
      </div>

      <p className="mt-1.5 text-[13px] leading-[1.4] text-ink" aria-live="polite">
        {summary}
      </p>

      {verdict?.motive && MOTIVE_COPY[verdict.motive] && verdict.status !== "PASS" && (
        <p className="mt-1 text-[12.5px] leading-[1.4] text-ink-soft">
          {MOTIVE_COPY[verdict.motive]}
        </p>
      )}

      {state.phase === "running" && (
        <p className="mt-1 font-mono text-[10.5px] text-ink-soft">
          {reported} of 4 gates have reported
        </p>
      )}

      {state.phase === "lost" && (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-[2px] border border-line px-2.5 py-2">
          <p className="text-[12px] leading-[1.4] text-block">
            {state.failure ?? "The event stream closed before the run finished."}
          </p>
          <Button variant="danger" size="sm" onClick={onRetry}>
            Retry the run
          </Button>
        </div>
      )}
    </section>
  );
}

/** The four gates, the verdict and the escalation, one row each. */
export function ChecksList({
  state,
  reading,
  mute,
  onToggleMute,
  faults,
  onToggleFault,
  controlsDisabled,
}: {
  state: RunState;
  reading: InstrumentReading;
  mute: GateName[];
  onToggleMute: (gate: GateName) => void;
  faults: FaultMap;
  onToggleFault: (gate: GateName) => void;
  /** Both switches lock while a run is in flight: they describe the next run. */
  controlsDisabled: boolean;
}) {
  const verdict = state.verdict;
  const probed = GATE_ORDER.filter((g) => state.gates[g].probe !== null).length;
  const escalation = state.escalation;
  const anyRunning = GATE_ORDER.some((g) => state.gates[g].status === "RUNNING");
  const now = useNow(anyRunning);

  return (
    <ol>
      {GATE_ORDER.map((gate) => {
        const card = state.gates[gate];
        const calibration = calibrationFor(reading, gate, card.reported);
        return (
          <CheckRow
            key={gate}
            name={gate}
            hue={GATE_DOT[gate]}
            status={card.status}
            line={gateLine(card)}
            under={calibration.text}
            underTone={calibration.tone}
            underPending={calibration.pending}
            counter={elapsedLine(card, now)}
            badges={
              <>
                {card.muted && (
                  <Badge tone="neutral" size="xs" title={MUTE_HELP}>
                    muted
                  </Badge>
                )}
                {card.fault && (
                  <Badge tone="amber" size="xs" title={FAULT_HELP}>
                    {card.fault} fault injected
                  </Badge>
                )}
              </>
            }
          >
            <dl className="space-y-2 text-[12.5px] leading-[1.5]">
              <div>
                <dt className="label-micro text-ink-soft">Source of truth</dt>
                <dd className="mt-1 text-ink">{card.sourceOfTruth}</dd>
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
                  <dd className="tabular mt-1 font-mono text-[11px] text-ink-soft">
                    {duration(card.done.elapsed_ms)}
                  </dd>
                </div>
              )}
              {card.done?.usage && (
                <div>
                  <dt className="label-micro text-ink-soft">Usage</dt>
                  <dd className="tabular mt-1 font-mono text-[10.5px] text-ink-soft">
                    {formatGateUsage(card.done.usage)}
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
                    disabled={controlsDisabled}
                    aria-describedby={`mute-help-${gate}`}
                  >
                    Mute telemetry
                  </Switch>
                </TooltipTrigger>
                <TooltipContent side="left">
                  <span className="block max-w-[34ch]">{MUTE_HELP}</span>
                </TooltipContent>
              </Tooltip>
              <p id={`mute-help-${gate}`} className="mt-1.5 text-[11.5px] leading-[1.45] text-ink-soft">
                {MUTE_HELP}
              </p>
            </div>

            {FAULT_GATES.includes(gate) && (
              <div className="mt-3 border-t border-line pt-3">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Switch
                      checked={Boolean(faults[gate])}
                      onCheckedChange={() => onToggleFault(gate)}
                      disabled={controlsDisabled}
                      aria-describedby={`fault-help-${gate}`}
                    >
                      Inject a fault
                    </Switch>
                  </TooltipTrigger>
                  <TooltipContent side="left">
                    <span className="block max-w-[34ch]">{FAULT_HELP}</span>
                  </TooltipContent>
                </Tooltip>
                <p id={`fault-help-${gate}`} className="mt-1.5 text-[11.5px] leading-[1.45] text-ink-soft">
                  {FAULT_HELP}
                </p>
              </div>
            )}

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
        under={
          state.verdictStatus === "PENDING" || state.verdictStatus === "RUNNING"
            ? "Waits for the four gates, then asks Grafana four PromQL questions per gate through mcp-grafana"
            : `${probed} of 4 gates probed through mcp-grafana`
        }
      >
        <dl className="space-y-2 text-[12.5px] leading-[1.5]">
          <div>
            <dt className="label-micro text-ink-soft">Source of truth</dt>
            <dd className="mt-1 text-ink">
              Grafana: error rate, seconds since last success, calibration catches over 7 days
            </dd>
          </div>
          {GATE_ORDER.filter((gate) => state.gates[gate].probe).map((gate) => {
            const probe = state.gates[gate].probe;
            if (!probe) return null;
            return (
              <div key={gate}>
                <dt className="label-micro text-ink-soft">{gate}</dt>
                <dd className="mt-1 font-mono text-[11px] text-ink-soft">
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
                className="text-[12.5px] text-accent underline underline-offset-[3px]"
              >
                Open the incident
              </a>
            )}
            <p className="label-micro mt-3 text-ink-soft">What the escalation agent returned</p>
            <Evidence value={escalation} />
          </>
        ) : (
          <p className="text-[12.5px] leading-[1.5] text-ink-soft">
            An escalation is opened only when the verdict says a human has to arbitrate.
          </p>
        )}
      </CheckRow>
    </ol>
  );
}
