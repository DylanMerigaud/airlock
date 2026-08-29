"use client";

import { GATE_ORDER, type GateName, type Terminal } from "@/lib/events";
import { splitTimecodes } from "@/lib/timecodes";
import type { GateCardState } from "@/lib/use-run";

/**
 * One sentence a gate wrote about the clip, in the order the gates reported.
 * The thread beside the player is this list, oldest first.
 */
export type Finding = {
  key: string;
  gate: GateName;
  status: Terminal;
  text: string;
  /** The first second of the clip the sentence names, when it names one. */
  seconds: number | null;
};

function firstSecond(text: string): number | null {
  for (const part of splitTimecodes(text)) {
    if (part.kind === "time") return part.seconds;
  }
  return null;
}

export function buildFindings(gates: Record<GateName, GateCardState>): Finding[] {
  const settled = GATE_ORDER.filter((gate) => gates[gate].done !== null).sort(
    (a, b) => (gates[a].settledAt ?? 0) - (gates[b].settledAt ?? 0),
  );

  const findings: Finding[] = [];
  for (const gate of settled) {
    const done = gates[gate].done;
    if (!done) continue;
    const reasons = done.reasons?.length ? done.reasons : [`${gate} ${done.status}`];
    reasons.forEach((text, index) => {
      findings.push({
        key: `${gate}-${index}`,
        gate,
        status: done.status,
        text,
        seconds: firstSecond(text),
      });
    });
  }
  return findings;
}

/**
 * A verdict reason that no gate already said. The gate sentences live in the
 * thread; what is left here is what the verdict itself added, such as a control
 * that Grafana says is unavailable.
 */
export function verdictNotes(reasons: string[], findings: Finding[]): string[] {
  return reasons.filter((reason) => !findings.some((finding) => reason.includes(finding.text)));
}
