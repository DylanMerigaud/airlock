import { NextResponse } from "next/server";
import { readHealth, type HealthPayload } from "@/lib/health";
import { cached } from "@/lib/grafana";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const get = cached<HealthPayload>(20_000);

export async function GET() {
  try {
    const payload = await get(readHealth);
    return NextResponse.json(payload, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return NextResponse.json(
      {
        ok: false,
        mock: process.env.AIRLOCK_MOCK === "1",
        gates: [],
        error: message,
        read_at: new Date().toISOString(),
      } satisfies HealthPayload,
      { headers: { "Cache-Control": "no-store" } },
    );
  }
}
