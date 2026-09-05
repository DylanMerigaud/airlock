/**
 * The human half of the loop: who can sign a review, and the shape the resolve
 * route answers. Shared by the route (server) and the Record segment (client).
 */

/** The roles a reviewer can sign as; the route refuses anything else. */
export const REVIEWER_ROLES = ["clearance owner (legal)", "agency", "platform on-call"] as const;
export type ReviewerRole = (typeof REVIEWER_ROLES)[number];

/** The role a Queue resolve should sign as, from the incident's own `owner` label: the button beside the
 *  owner column must not sign every incident as platform on-call regardless of who it was routed to
 *  (found live, 2026-09-05). Falls back to platform on-call for an incident opened before the label
 *  existed, or any other owner value. */
export function reviewerRoleForOwner(owner: string | null): ReviewerRole {
  if (owner === "clearance") return "clearance owner (legal)";
  return "platform on-call";
}

export type ResolvePayload = {
  ok: boolean;
  mock: boolean;
  incident_id: string | null;
  /** The status Grafana Incident reports after the update ("resolved"), or null when no incident was given. */
  status: string | null;
  annotation_id: number | null;
  reviewer_role: string;
  error: string | null;
  at: string;
};

/** The one line the annotation carries: the verdict, the asset, the run. */
export function verdictSummary(status: string | undefined, motive: string | undefined, assetId: string | undefined, runId: string | undefined): string {
  const head = `${status ?? "?"}${motive ? ` (${motive})` : ""}`;
  return `${head}${assetId ? ` ${assetId}` : ""}${runId ? ` run ${runId}` : ""}`;
}
