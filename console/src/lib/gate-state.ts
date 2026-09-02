/**
 * What the console says about a gate from Grafana's three numbers, before a run.
 * Shared by the health route (server) and the instrument lines (client).
 *
 * degraded: errors in the last 15 minutes. unproven: no success sample in 7 days.
 * uncalibrated: no injected defect caught in 7 days. idle: no error, but the last
 * success is older than 900 s; the gates run before the verdict asks Grafana, so
 * a run re-proves an idle gate on its own. healthy: none of the above.
 */
export type GateState = "healthy" | "idle" | "degraded" | "unproven" | "uncalibrated";

/** The staleness bound the verdict's R1 rule applies, in seconds. */
export const STALE_AFTER_S = 900;

export function deriveState(
  errorRate: number | null,
  sinceSuccess: number | null,
  catches: number | null,
): GateState {
  if (errorRate !== null && errorRate > 0) return "degraded";
  if (sinceSuccess === null) return "unproven";
  if (catches === null || catches === 0) return "uncalibrated";
  if (sinceSuccess > STALE_AFTER_S) return "idle";
  return "healthy";
}
