"use client";

import { type GateName, type ReportedInstrument } from "@/lib/events";
import { STALE_AFTER_S, uncalibratedBecause, type GateState } from "@/lib/gate-state";
import { percent, shortSeconds } from "@/lib/utils";

/** One hue per gate, matched to the scrubber markers. */
export const GATE_DOT: Record<GateName, string> = {
  rights: "bg-gate-rights",
  claim: "bg-gate-claim",
  brand: "bg-gate-brand",
  provenance: "bg-gate-provenance",
};

export type GateHealthView = {
  gate: GateName;
  state: GateState;
  calibrated?: boolean;
  error_rate_15m: number | null;
  seconds_since_success: number | null;
  calibration_catches_7d: number | null;
  /** 1 caught, 0 missed, null never calibrated. Absent from payloads recorded before it was asked. */
  last_calibration_caught?: number | null;
  /** Runs behind error_rate_15m in the last 15 minutes; needed with the ratio for the majority rule. */
  runs_15m?: number | null;
  exprs: Record<string, string>;
};

/**
 * What "caught N injected defects" means, for a reader who is not the engineer
 * who built the calibration: shown as the line's tooltip and, in words, in the
 * expanded row.
 */
export const CALIBRATION_HELP =
  "Calibration: every six hours Airlock injects a known defect into each gate and checks the gate catches it. This line counts the catches over the last 7 days and says whether the latest one caught its defect.";

export const CALIBRATION_CLAUSE =
  "(calibration: the gate caught the defects injected into it over the last 7 days)";

export type HealthView = {
  ok: boolean;
  mock: boolean;
  gates: GateHealthView[];
  error: string | null;
};

/**
 * A stretch during which /api/health or /api/stats answers ok: false. The
 * console retries on its own (use-instruments.ts); what the screen shows
 * meanwhile is a placeholder, then "unavailable" once the budget is spent.
 */
export type Outage = {
  /** When the current outage began, ms since epoch. */
  since: number;
  /** Plain words for the screen, never the raw error. */
  reason: string;
  /** The error text as the route returned it, for a tooltip. */
  raw: string;
  /** Grafana Cloud is waking a paused stack (503, "Loading"). */
  starting: boolean;
  /** The fast retry budget is spent; the console now retries every minute. */
  exhausted: boolean;
};

/** What the calibration line has to read from: the last good reading and the outage, if any. */
export type InstrumentReading = {
  health: HealthView | null;
  loading: boolean;
  outage: Outage | null;
};

export function describeOutage(error: string | null | undefined): { reason: string; starting: boolean } {
  const text = error ?? "";
  if (/loading|503/i.test(text)) {
    return { reason: "Grafana Cloud is starting, retrying", starting: true };
  }
  return { reason: "Grafana did not answer, retrying", starting: false };
}

export type Calibration = {
  text: string;
  tone: "quiet" | "amber" | "block";
  detail: string;
  /** No reading yet: the row draws a placeholder instead of the text. */
  pending?: boolean;
  /** Plain words for what the line counts, when it counts calibration catches. */
  help?: string;
};

function localCalibration(reading: InstrumentReading, gate: GateName): Calibration {
  const { health, loading, outage } = reading;

  if (!health) {
    if (loading || (outage && !outage.exhausted)) {
      return {
        text: "reading Grafana",
        tone: "quiet",
        detail: outage
          ? `${outage.reason}. ${outage.raw}`
          : "The console is querying the Grafana datasource.",
        pending: true,
      };
    }
    return {
      text: "calibration unavailable",
      tone: "block",
      detail: outage ? `${outage.reason}. ${outage.raw}` : "The console could not reach Grafana.",
    };
  }

  const entry = health.gates.find((g) => g.gate === gate);
  if (!entry) {
    return {
      text: "calibration unavailable",
      tone: "block",
      detail: "Grafana returned no series for this gate.",
    };
  }

  const lastCaught = entry.last_calibration_caught ?? null;
  const detail = [
    `error_rate_15m ${entry.error_rate_15m === null ? "no sample" : entry.error_rate_15m.toFixed(2)}`,
    `runs_15m ${entry.runs_15m === null ? "no sample" : entry.runs_15m}`,
    `seconds_since_success ${entry.seconds_since_success === null ? "no sample" : entry.seconds_since_success.toFixed(1)}`,
    `calibration_catches_7d ${entry.calibration_catches_7d === null ? "no sample" : entry.calibration_catches_7d}`,
    `last_calibration_caught ${lastCaught === null ? "no sample" : lastCaught > 0 ? "1 (caught)" : "0 (missed)"}`,
  ].join("\n");

  if (entry.state === "degraded") {
    return {
      text: `degraded: error rate ${percent(entry.error_rate_15m)} over ${entry.runs_15m ?? 0} run${entry.runs_15m === 1 ? "" : "s"} (a majority)`,
      tone: "amber",
      detail,
    };
  }

  if (entry.state === "unproven") {
    return { text: "unproven: no success seen in 7 d", tone: "amber", detail };
  }

  if (entry.state === "uncalibrated") {
    const because = uncalibratedBecause(entry.calibration_catches_7d, lastCaught);
    if (because === "missed") {
      return {
        text: `last calibration run MISSED its defect: ADVISORY (${entry.calibration_catches_7d ?? 0} caught earlier in 7d)`,
        tone: "amber",
        detail: `${detail}\nthe gate did not catch the defect injected into it last time, so its PASS is advisory until it does`,
        help: CALIBRATION_HELP,
      };
    }
    return { text: "never calibrated: ADVISORY", tone: "amber", detail, help: CALIBRATION_HELP };
  }

  if (entry.state === "idle") {
    return {
      text: `idle: last success ${shortSeconds(entry.seconds_since_success)} ago, the run re-proves it`,
      tone: "quiet",
      detail: `${detail}\nidle past ${STALE_AFTER_S} s without a success; the gates run before the verdict asks Grafana`,
    };
  }

  const catches = entry.calibration_catches_7d ?? 0;
  return {
    text: `caught ${catches} injected defect${catches === 1 ? "" : "s"} in 7d, last success ${shortSeconds(entry.seconds_since_success)} ago`,
    tone: "quiet",
    detail,
    help: CALIBRATION_HELP,
  };
}

/**
 * What the verdict agent read out of Grafana during the run wins over anything
 * the console recomputes on the side: it is the reading the decision was made
 * on. The recomputed line stays as the fallback and as the tooltip numbers.
 */
export function calibrationFor(
  reading: InstrumentReading,
  gate: GateName,
  reported?: ReportedInstrument | null,
): Calibration {
  const local = localCalibration(reading, gate);
  if (!reported?.calibration) return local;

  // Amber only when the verdict itself saw a problem: not calibrated, this run's event not seen, the
  // reading unavailable, or the error ratio at the block line (the majority clause prints the run count).
  // The verdict's own boolean when it sent one (every run since 2026-09-05); the prose test only for
  // recordings that predate it.
  const degraded =
    reported.calibrated === false ||
    (reported.unavailable ?? (reported.health !== undefined && /NOT seen|could not be read|error rate .* \(/i.test(reported.health)));

  // The tooltip must never present the console's own background poll as what the verdict read: that
  // is a different query at a different second and the numbers disagree (found by the third panel,
  // 2026-09-05). Show the verdict's own PromQL answers when the probe stage sent them; only fall back
  // to the console's recomputed numbers, clearly labelled as such, when it did not.
  const verdictAnswers = reported.answers
    ? Object.entries(reported.answers)
        .map(([key, a]) => `${key} ${a.value === null ? "no sample" : a.value.toFixed(2)}`)
        .join("\n")
    : null;
  const detail = verdictAnswers
    ? `Read from Grafana by the verdict agent during this run.\n${verdictAnswers}`
    : `Read from Grafana by the verdict agent during this run: ${reported.health ?? reported.calibration}.\n` +
      `The console's own reading of the same gate, taken separately, for comparison:\n${local.detail}`;

  return {
    text: reported.health ? `${reported.calibration}, ${reported.health}` : reported.calibration,
    tone: degraded ? "amber" : "quiet",
    detail,
    help: /injected defect|calibration/i.test(reported.calibration) ? CALIBRATION_HELP : local.help,
  };
}
