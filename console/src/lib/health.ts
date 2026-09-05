import "server-only";
import { GATE_ORDER, type GateName } from "@/lib/events";
import { grafanaInstant, isMock, type InstantQuery } from "@/lib/grafana";
import { deriveState, isCalibrated, type GateState } from "@/lib/gate-state";
import promql from "@/lib/promql.json";

export { deriveState, type GateState };

export type GateHealth = {
  gate: GateName;
  state: GateState;
  /** airlock/verdict.py GateHealth.calibrated, computed from the two calibration answers. */
  calibrated: boolean;
  error_rate_15m: number | null;
  seconds_since_success: number | null;
  calibration_catches_7d: number | null;
  /** 1 when the last calibration run caught its defect, 0 when it missed, null never calibrated. */
  last_calibration_caught: number | null;
  /** The number of runs the error rate was computed over in the last 15 minutes (the verdict's own
   *  majority clause needs this alongside the ratio: one error out of one run is not a block). */
  runs_15m: number | null;
  /** Every expression asked, keyed as in promql.json (the verdict's own keys). */
  exprs: Record<string, string>;
  note?: string;
};

export type HealthPayload = {
  ok: boolean;
  mock: boolean;
  gates: GateHealth[];
  error: string | null;
  read_at: string;
};

/**
 * The PromQL for one gate, verbatim from airlock/verdict.py through
 * scripts/export_promql.py. The console asks every expression the verdict asks,
 * in the verdict's own words, and nothing it wrote itself.
 */
export function exprs(gate: GateName): Record<string, string> {
  return { ...promql.gates[gate] };
}

/** The four answers the state is derived from; the rest ride along in `exprs` for the tooltip. */
type Readings = {
  error_rate_15m: number | null;
  seconds_since_success: number | null;
  calibration_catches_7d: number | null;
  last_calibration_caught: number | null;
  runs_15m: number | null;
};

function toGateHealth(gate: GateName, r: Readings, note?: string): GateHealth {
  return {
    gate,
    state: deriveState(r.error_rate_15m, r.seconds_since_success, r.calibration_catches_7d, r.last_calibration_caught, r.runs_15m),
    calibrated: isCalibrated(r.calibration_catches_7d, r.last_calibration_caught),
    ...r,
    exprs: exprs(gate),
    note,
  };
}

/**
 * Mirrors console/fixtures/run-nimbus-block.jsonl so mock mode is coherent:
 * error rate, seconds since success, catches in 7 d, last calibration caught.
 */
const MOCK_READINGS: Record<GateName, [number, number, number, number, number]> = {
  rights: [0, 10.4, 1, 1, 3],
  claim: [0.3333, 33.1, 1, 1, 3],
  brand: [0, 46.0, 1, 1, 2],
  provenance: [0, 56.8, 2, 1, 4],
};

export async function readHealth(): Promise<HealthPayload> {
  const read_at = new Date().toISOString();

  if (isMock()) {
    return {
      ok: true,
      mock: true,
      read_at,
      error: null,
      gates: GATE_ORDER.map((gate) => {
        const [error_rate_15m, seconds_since_success, calibration_catches_7d, last_calibration_caught, runs_15m] =
          MOCK_READINGS[gate];
        return toGateHealth(gate, {
          error_rate_15m,
          seconds_since_success,
          calibration_catches_7d,
          last_calibration_caught,
          runs_15m,
        });
      }),
    };
  }

  const queries: InstantQuery[] = [];
  for (const gate of GATE_ORDER) {
    for (const [key, expr] of Object.entries(exprs(gate))) {
      queries.push({ refId: `${gate}__${key}`, expr });
    }
  }

  const answers = await grafanaInstant(queries);

  return {
    ok: true,
    mock: false,
    read_at,
    error: null,
    gates: GATE_ORDER.map((gate) => {
      const value = (key: string) => answers[`${gate}__${key}`]?.value ?? null;
      const note = Object.keys(exprs(gate))
        .map((key) => answers[`${gate}__${key}`]?.error)
        .filter(Boolean)
        .join("; ");
      return toGateHealth(
        gate,
        {
          error_rate_15m: value("error_rate_15m"),
          seconds_since_success: value("seconds_since_success"),
          calibration_catches_7d: value("calibration_catches_7d"),
          last_calibration_caught: value("last_calibration_caught"),
          runs_15m: value("runs_15m"),
        },
        note || undefined,
      );
    }),
  };
}
