/**
 * What the console says about a gate from Grafana's five numbers, before a run.
 * Shared by the health route (server) and the instrument lines (client).
 *
 * The numbers are the answers to the PromQL in promql.json, which is exported
 * from airlock/verdict.py (scripts/export_promql.py) so the console never asks
 * fewer questions than the verdict. `isCalibrated` mirrors GateHealth.calibrated
 * on the Python side exactly: catches in 7 d, AND the last calibration run
 * caught its defect.
 *
 * degraded: a majority of the last few runs erred (the same ERROR_RATIO_BLOCK and
 * ERROR_RUNS_MIN the verdict itself blocks on; one error alone reads healthy, as it
 * does in the verdict). unproven: no success sample in 7 days. uncalibrated: no
 * injected defect caught in 7 days, or the last calibration run missed its defect.
 * idle: no error, but the last success is older than STALE_AFTER_S; the gates run
 * before the verdict asks Grafana, so a run re-proves an idle gate on its own.
 * healthy: none of the above.
 */
import promql from "@/lib/promql.json";

export type GateState = "healthy" | "idle" | "degraded" | "unproven" | "uncalibrated";

/** The staleness bound in seconds, from the same export as the PromQL. */
export const STALE_AFTER_S: number = promql.stale_after_s;

/** R1's majority clause (airlock/verdict.py GateHealth.errors_are_majority), from the same export. */
export const ERROR_RATIO_BLOCK: number = promql.error_ratio_block;
export const ERROR_RUNS_MIN: number = promql.error_runs_min;

/** airlock/verdict.py GateHealth.errors_are_majority, line for line: a single error is not a block, a
 *  majority of recent runs failing is. */
export function errorsAreMajority(errorRate: number | null, runs: number | null): boolean {
  return errorRate !== null && errorRate >= ERROR_RATIO_BLOCK && (runs ?? 0) >= ERROR_RUNS_MIN;
}

/** The window the calibration questions read, as written in the expressions. */
export const CALIBRATION_WINDOW = "7d";

/** airlock/verdict.py GateHealth.calibrated, line for line. */
export function isCalibrated(catches: number | null, lastCaught: number | null): boolean {
  if ((catches ?? 0) <= 0) return false;
  return lastCaught === null || lastCaught > 0;
}

/** airlock/verdict.py GateHealth.calibration_note, line for line. */
export function calibrationNote(catches: number | null, lastCaught: number | null): string {
  if ((catches ?? 0) <= 0) return `no injected defect caught in ${CALIBRATION_WINDOW}`;
  if (lastCaught !== null && lastCaught <= 0) {
    return `last calibration run MISSED its defect (${Math.trunc(catches as number)} caught earlier in ${CALIBRATION_WINDOW})`;
  }
  return `caught ${Math.trunc(catches as number)} injected defect(s) in ${CALIBRATION_WINDOW}`;
}

/** Why a gate reads uncalibrated: it never caught one, or its last run missed. */
export function uncalibratedBecause(
  catches: number | null,
  lastCaught: number | null,
): "never" | "missed" | null {
  if ((catches ?? 0) <= 0) return "never";
  if (lastCaught !== null && lastCaught <= 0) return "missed";
  return null;
}

export function deriveState(
  errorRate: number | null,
  sinceSuccess: number | null,
  catches: number | null,
  lastCaught: number | null = null,
  runs: number | null = null,
): GateState {
  if (errorsAreMajority(errorRate, runs)) return "degraded";
  if (sinceSuccess === null) return "unproven";
  if (!isCalibrated(catches, lastCaught)) return "uncalibrated";
  if (sinceSuccess > STALE_AFTER_S) return "idle";
  return "healthy";
}
