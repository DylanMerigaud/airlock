import { NextResponse } from "next/server";
import { callerKey, RUN_LIMIT_PER_HOUR, takeRunToken } from "@/lib/run-limit";
import { isMock } from "@/lib/grafana";
import { createAnnotation, resolveIncident, getIncident } from "@/lib/incidents";
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
  // The console has no login (a demo posture, said in the README): a caller resolves at most
  // RUN_LIMIT_PER_HOUR incidents an hour, and the annotation records where the review came from.
  const caller = callerKey(request);
  const allowed = takeRunToken(caller, Date.now(), "resolve");
  if (!allowed.ok) {
    return NextResponse.json(
      { error: `Too many reviews from this address: ${RUN_LIMIT_PER_HOUR} per hour. Try again in ${allowed.retryAfterS} s.` },
      { status: 429, headers: { "Retry-After": String(allowed.retryAfterS) } },
    );
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
      // Only an Airlock incident can be resolved from here: the route reads it back first and refuses a
      // title the escalation agent did not write, so the console cannot close someone else's incident.
      const incident = await getIncident(incidentId);
      if (!incident.title.startsWith("Airlock needs a human")) {
        return NextResponse.json({ error: `Incident ${incidentId} is not an Airlock incident.` }, { status: 403 });
      }
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
