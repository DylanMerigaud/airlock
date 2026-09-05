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
};

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
