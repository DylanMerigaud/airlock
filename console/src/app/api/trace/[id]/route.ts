import { NextResponse } from "next/server";
import { isMock } from "@/lib/grafana";
import { readTrace, type TracePayload } from "@/lib/trace";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TRACE_ID_RE = /^[0-9a-f]{16,32}$/i;

/** One mock span so the Trace view has something to render without a live trace. */
function mockTrace(traceId: string): TracePayload {
  return {
    ok: true,
    traceId,
    serviceName: "airlock",
    error: null,
    spans: [
      { spanId: "aa11", parentSpanId: null, name: "invoke_workflow airlock", scope: "gcp.vertex.agent", startNs: 0, durationMs: 4200, status: "OK", attributes: {} },
      { spanId: "bb22", parentSpanId: "aa11", name: "airlock.gate.rights", scope: "airlock", startNs: 100_000_000, durationMs: 3800, status: "OK", attributes: { "airlock.gate": "rights" } },
    ],
  };
}

/**
 * A trace proxied through the server's own Grafana credentials, so a judge with no Grafana login
 * can still see the span tree the Record and the Trace view link to (third panel, 2026-09-05: the
 * Explore link the product hands out opens a login wall for anyone but the entrant).
 */
export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!TRACE_ID_RE.test(id)) {
    return NextResponse.json({ error: `"${id}" is not a trace id.` } satisfies { error: string }, { status: 400 });
  }
  if (isMock()) {
    return NextResponse.json(mockTrace(id), { headers: { "Cache-Control": "no-store" } });
  }
  const payload = await readTrace(id);
  return NextResponse.json(payload, {
    status: payload.ok ? 200 : 502,
    headers: { "Cache-Control": "no-store" },
  });
}
