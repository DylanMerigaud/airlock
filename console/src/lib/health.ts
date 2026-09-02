import "server-only";
import { GATE_ORDER, type GateName } from "@/lib/events";
import { grafanaInstant, isMock, type InstantQuery } from "@/lib/grafana";
import { deriveState, type GateState } from "@/lib/gate-state";

export { deriveState, type GateState };

export type GateHealth = {
  gate: GateName;
  state: GateState;
  error_rate_15m: number | null;
  seconds_since_success: number | null;
  calibration_catches_7d: number | null;
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

export function exprs(gate: GateName) {
  return {
    error_rate_15m: `sum(sum_over_time(airlock_gate_errors_total{gate="${gate}"}[15m])) / clamp_min(sum(sum_over_time(airlock_gate_runs_total{gate="${gate}"}[15m])), 1)`,
    seconds_since_success: `time() - max(max_over_time(airlock_gate_last_success_ts{gate="${gate}"}[7d]))`,
    calibration_catches_7d: `sum(sum_over_time(airlock_calibration_catches_total{gate="${gate}"}[7d]))`,
  };
}

/** Mirrors console/fixtures/run-nimbus-block.jsonl so mock mode is coherent. */
const MOCK_READINGS: Record<GateName, [number, number, number]> = {
  rights: [0, 10.4, 1],
  claim: [0.3333, 33.1, 1],
  brand: [0, 46.0, 1],
  provenance: [0, 56.8, 2],
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
        const [errorRate, since, catches] = MOCK_READINGS[gate];
        return {
          gate,
          state: deriveState(errorRate, since, catches),
          error_rate_15m: errorRate,
          seconds_since_success: since,
          calibration_catches_7d: catches,
          exprs: exprs(gate),
        };
      }),
    };
  }

  const queries: InstantQuery[] = [];
  for (const gate of GATE_ORDER) {
    const e = exprs(gate);
    queries.push({ refId: `${gate}__error_rate_15m`, expr: e.error_rate_15m });
    queries.push({ refId: `${gate}__seconds_since_success`, expr: e.seconds_since_success });
    queries.push({ refId: `${gate}__calibration_catches_7d`, expr: e.calibration_catches_7d });
  }

  const answers = await grafanaInstant(queries);

  return {
    ok: true,
    mock: false,
    read_at,
    error: null,
    gates: GATE_ORDER.map((gate) => {
      const errorRate = answers[`${gate}__error_rate_15m`]?.value ?? null;
      const since = answers[`${gate}__seconds_since_success`]?.value ?? null;
      const catches = answers[`${gate}__calibration_catches_7d`]?.value ?? null;
      const note = [
        answers[`${gate}__error_rate_15m`]?.error,
        answers[`${gate}__seconds_since_success`]?.error,
        answers[`${gate}__calibration_catches_7d`]?.error,
      ]
        .filter(Boolean)
        .join("; ");
      return {
        gate,
        state: deriveState(errorRate, since, catches),
        error_rate_15m: errorRate,
        seconds_since_success: since,
        calibration_catches_7d: catches,
        exprs: exprs(gate),
        note: note || undefined,
      };
    }),
  };
}
