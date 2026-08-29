import { NextResponse } from "next/server";
import { readHealth } from "@/lib/health";
import { cached, grafanaInstant, isMock } from "@/lib/grafana";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export type StatsPayload = {
  ok: boolean;
  mock: boolean;
  checked_7d: number | null;
  passed_7d: number | null;
  blocked_7d: number | null;
  incidents_7d: number | null;
  gates_calibrated: number | null;
  gates_total: number;
  cost_per_check_usd_7d: number | null;
  error: string | null;
  read_at: string;
};

const EXPRS = {
  blocked: 'sum(sum_over_time(airlock_verdict_total{status="BLOCK"}[7d]))',
  passed: 'sum(sum_over_time(airlock_verdict_total{status="PASS"}[7d]))',
  incidents: "sum(sum_over_time(airlock_incident_total[7d]))",
  costPerCheck:
    "sum(sum_over_time(airlock_verdict_cost_usd[7d])) / clamp_min(sum(sum_over_time(airlock_verdict_total[7d])), 1)",
};

const get = cached<StatsPayload>(20_000);

async function readStats(): Promise<StatsPayload> {
  const read_at = new Date().toISOString();

  if (isMock()) {
    const health = await readHealth();
    const passed = 18;
    const blocked = 7;
    return {
      ok: true,
      mock: true,
      checked_7d: passed + blocked,
      passed_7d: passed,
      blocked_7d: blocked,
      incidents_7d: 3,
      gates_calibrated: health.gates.filter((g) => (g.calibration_catches_7d ?? 0) > 0).length,
      gates_total: 4,
      cost_per_check_usd_7d: 0.41,
      error: null,
      read_at,
    };
  }

  const [answers, health] = await Promise.all([
    grafanaInstant([
      { refId: "blocked", expr: EXPRS.blocked },
      { refId: "passed", expr: EXPRS.passed },
      { refId: "incidents", expr: EXPRS.incidents },
      { refId: "costPerCheck", expr: EXPRS.costPerCheck },
    ]),
    readHealth(),
  ]);

  const passed = answers.passed?.value ?? null;
  const blocked = answers.blocked?.value ?? null;
  const checked = passed === null && blocked === null ? null : (passed ?? 0) + (blocked ?? 0);

  return {
    ok: true,
    mock: false,
    checked_7d: checked,
    passed_7d: passed,
    blocked_7d: blocked,
    incidents_7d: answers.incidents?.value ?? null,
    gates_calibrated: health.gates.filter((g) => (g.calibration_catches_7d ?? 0) > 0).length,
    gates_total: 4,
    cost_per_check_usd_7d: answers.costPerCheck?.value ?? null,
    error: null,
    read_at,
  };
}

export async function GET() {
  try {
    const payload = await get(readStats);
    return NextResponse.json(payload, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return NextResponse.json(
      {
        ok: false,
        mock: isMock(),
        checked_7d: null,
        passed_7d: null,
        blocked_7d: null,
        incidents_7d: null,
        gates_calibrated: null,
        gates_total: 4,
        cost_per_check_usd_7d: null,
        error: message,
        read_at: new Date().toISOString(),
      } satisfies StatsPayload,
      { headers: { "Cache-Control": "no-store" } },
    );
  }
}
