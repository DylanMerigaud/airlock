/** The shapes of Grafana incidents as the console shows them; shared by the server lib, the routes and the client. */

export type IncidentPreview = {
  id: string;
  title: string;
  status: string;
  severity: string;
  isDrill: boolean;
  createdAt: string;
  closedAt: string | null;
  /** Parsed from the title the escalation agent writes: "Airlock needs a human: <motive> on <asset id>". */
  motive: string | null;
  assetId: string | null;
  url: string;
  /**
   * Who the escalation routed the incident to, from its `owner` label: "clearance"
   * (paperwork lifts the block) or "platform" (a control was unavailable, uncalibrated
   * or in error). Previews carry no labels, so the route reads it per incident; null
   * when the incident has no owner label (opened before the escalation wrote one).
   */
  owner: string | null;
  /** False when the labels were not read for this row (beyond the per-refresh budget, or the read failed). */
  ownerRead: boolean;
};

/** The words the Queue prints for an owner label. */
export function ownerLabel(owner: string): string {
  if (owner === "clearance") return "clearance owner";
  if (owner === "platform") return "platform on-call";
  return `${owner} owner`;
}

export type IncidentDetail = IncidentPreview & {
  labels: Array<{ key: string; label: string }>;
  summary: string;
  durationSeconds: number | null;
};

export type IncidentsPayload = {
  ok: boolean;
  mock: boolean;
  incidents: IncidentPreview[];
  error: string | null;
  read_at: string;
};
