import { NextResponse } from "next/server";
import { isMock } from "@/lib/grafana";
import type { IncidentPreview, IncidentsPayload } from "@/lib/incident-types";
import { queryOpenIncidents, withOwners } from "@/lib/incidents";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** What mock mode shows in the queue: two open drills shaped like the real ones. */
const MOCK_INCIDENTS: IncidentPreview[] = [
  {
    id: "29",
    title: "Airlock needs a human: control unavailable on nimbus-clean-clip",
    status: "active",
    severity: "Minor",
    isDrill: true,
    createdAt: "2026-09-05T05:20:14Z",
    closedAt: null,
    motive: "control unavailable",
    assetId: "nimbus-clean-clip",
    url: "https://narrowsubmarine1895.grafana.net/a/grafana-irm-app/incidents/29",
    owner: "platform",
    ownerRead: true,
  },
  {
    id: "26",
    title: "Airlock needs a human: content on nimbus-test-clip",
    status: "active",
    severity: "Minor",
    isDrill: true,
    createdAt: "2026-09-05T03:30:12Z",
    closedAt: null,
    motive: "content",
    assetId: "nimbus-test-clip",
    url: "https://narrowsubmarine1895.grafana.net/a/grafana-irm-app/incidents/26",
    owner: "clearance",
    ownerRead: true,
  },
];

/**
 * The open Airlock incidents in Grafana, the queue a reviewer works through. Each
 * row carries its owner (the escalation's `owner` label), read per incident since
 * the preview API returns no labels; at most 20 rows per refresh.
 */
export async function GET() {
  const read_at = new Date().toISOString();
  if (isMock()) {
    return NextResponse.json(
      { ok: true, mock: true, incidents: MOCK_INCIDENTS, error: null, read_at } satisfies IncidentsPayload,
      { headers: { "Cache-Control": "no-store" } },
    );
  }
  try {
    const incidents = await withOwners(await queryOpenIncidents());
    return NextResponse.json({ ok: true, mock: false, incidents, error: null, read_at } satisfies IncidentsPayload, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return NextResponse.json({ ok: false, mock: false, incidents: [], error: message, read_at } satisfies IncidentsPayload, {
      headers: { "Cache-Control": "no-store" },
    });
  }
}
