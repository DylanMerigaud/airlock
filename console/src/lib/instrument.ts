"use client";

import { type GateName, type ReportedInstrument } from "@/lib/events";
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
  state: "healthy" | "degraded" | "uncalibrated";
  error_rate_15m: number | null;
  seconds_since_success: number | null;
  calibration_catches_7d: number | null;
  exprs: Record<string, string>;
};

export type HealthView = {
  ok: boolean;
  mock: boolean;
  gates: GateHealthView[];
  error: string | null;
};

export type Calibration = {
  text: string;
  tone: "quiet" | "amber" | "block";
  detail: string;
};

function localCalibration(
  health: HealthView | null,
  loading: boolean,
  gate: GateName,
): Calibration {
  if (loading) {
    return {
      text: "reading Grafana",
      tone: "quiet",
      detail: "The console is querying the Grafana datasource.",
    };
  }
  if (!health || !health.ok) {
    return {
      text: "calibration unavailable",
      tone: "block",
      detail: health?.error ?? "The console could not reach Grafana.",
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

  const detail = [
    `error_rate_15m ${entry.error_rate_15m === null ? "no sample" : entry.error_rate_15m.toFixed(2)}`,
    `seconds_since_success ${entry.seconds_since_success === null ? "no sample" : entry.seconds_since_success.toFixed(1)}`,
    `calibration_catches_7d ${entry.calibration_catches_7d === null ? "no sample" : entry.calibration_catches_7d}`,
  ].join("\n");

  if (entry.state === "degraded") {
    if (entry.error_rate_15m !== null && entry.error_rate_15m > 0) {
      return {
        text: `degraded: error rate ${percent(entry.error_rate_15m)}`,
        tone: "amber",
        detail,
      };
    }
    if (entry.seconds_since_success === null) {
      return { text: "degraded: no success in the last 7d", tone: "amber", detail };
    }
    return {
      text: `degraded: last success ${shortSeconds(entry.seconds_since_success)} ago`,
      tone: "amber",
      detail,
    };
  }

  if (entry.state === "uncalibrated") {
    return { text: "never calibrated: ADVISORY", tone: "amber", detail };
  }

  const catches = entry.calibration_catches_7d ?? 0;
  return {
    text: `caught ${catches} injected defect${catches === 1 ? "" : "s"} in 7d, last success ${shortSeconds(entry.seconds_since_success)} ago`,
    tone: "quiet",
    detail,
  };
}

/**
 * What the verdict agent read out of Grafana during the run wins over anything
 * the console recomputes on the side: it is the reading the decision was made
 * on. The recomputed line stays as the fallback and as the tooltip numbers.
 */
export function calibrationFor(
  health: HealthView | null,
  loading: boolean,
  gate: GateName,
  reported?: ReportedInstrument | null,
): Calibration {
  const local = localCalibration(health, loading, gate);
  if (!reported?.calibration) return local;

  const degraded =
    reported.calibrated === false ||
    (reported.health !== undefined && !/healthy/i.test(reported.health));

  return {
    text: reported.health ? `${reported.calibration}, ${reported.health}` : reported.calibration,
    tone: degraded ? "amber" : "quiet",
    detail: `Read from Grafana by the verdict agent during this run.\n${local.detail}`,
  };
}
