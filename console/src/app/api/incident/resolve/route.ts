import { NextResponse } from "next/server";
import { isMock } from "@/lib/grafana";
import { createAnnotation, resolveIncident } from "@/lib/incidents";
import { REVIEWER_ROLES, type ResolvePayload } from "@/lib/review";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Body = {
  incidentID?: unknown;
  reviewer_role?: unknown;
  /** The verdict summary the annotation carries: "BLOCK (control unavailable) nimbus-clean-clip run e-...". */
  summary?: unknown;
  asset_id?: unknown;
};

/**
 * The reviewer's decision, written where the run was written: the incident is
 * resolved through Grafana Incident (IncidentsService.UpdateStatus) and an
 * annotation tagged airlock, reviewed lands on the dashboard with the
 * reviewer's role and the verdict summary.
 */
export async function POST(request: Request) {
  const at = new Date().toISOString();
  let body: Body;
  try {
    body = (await request.json()) as Body;
  } catch {
    return NextResponse.json({ error: "Send a JSON body with incidentID, reviewer_role and summary." }, { status: 400 });
  }
  const role = typeof body.reviewer_role === "string" ? body.reviewer_role : "";
  if (!(REVIEWER_ROLES as readonly string[]).includes(role)) {
    return NextResponse.json({ error: `reviewer_role must be one of: ${REVIEWER_ROLES.join(", ")}.` }, { status: 400 });
  }
  const incidentId = typeof body.incidentID === "string" && /^\d+$/.test(body.incidentID) ? body.incidentID : null;
  const summary = typeof body.summary === "string" ? body.summary.slice(0, 600) : "no verdict summary given";
  const assetId = typeof body.asset_id === "string" ? body.asset_id.slice(0, 40) : null;

  if (isMock()) {
    return NextResponse.json({
      ok: true,
      mock: true,
      incident_id: incidentId,
      status: incidentId ? "resolved" : null,
      annotation_id: 0,
      reviewer_role: role,
      error: null,
      at,
    } satisfies ResolvePayload);
  }

  let status: string | null = null;
  let annotationId: number | null = null;
  const errors: string[] = [];
  if (incidentId) {
    try {
      status = (await resolveIncident(incidentId)).status;
    } catch (error) {
      errors.push(error instanceof Error ? error.message : String(error));
    }
  }
  try {
    const tags = ["airlock", "reviewed", ...(assetId ? [assetId] : []), process.env.AIRLOCK_RUNTIME || "console"];
    const text = `reviewed by a human (${role}): ${summary}${incidentId ? ` [incident ${incidentId} ${status ?? "not resolved"}]` : ""}`;
    annotationId = (await createAnnotation(text, tags)).id;
  } catch (error) {
    errors.push(error instanceof Error ? error.message : String(error));
  }
  return NextResponse.json({
    ok: errors.length === 0,
    mock: false,
    incident_id: incidentId,
    status,
    annotation_id: annotationId,
    reviewer_role: role,
    error: errors.length > 0 ? errors.join("; ") : null,
    at,
  } satisfies ResolvePayload);
}
