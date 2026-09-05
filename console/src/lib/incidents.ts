import "server-only";

import type { IncidentDetail, IncidentPreview } from "@/lib/incident-types";

/**
 * Grafana Incident (the IRM app) over its plugin resource API, with the service
 * account token the console already holds. The escalation agent opens incidents
 * through mcp-grafana; the console reads them back, and the reviewer's decision
 * closes them here and lands on the dashboard as an annotation.
 *
 * Verified on this stack on 2026-09-05: IncidentsService.UpdateStatus answers 200,
 * QueryIncidentPreviews with "status:active" returns the drills too (28 of 28).
 */

const IRM_PATH = "/api/plugins/grafana-irm-app/resources/api/v1/";
const TITLE_PREFIX = "Airlock needs a human: ";
const PREVIEW_LIMIT = 50;

export type { IncidentDetail, IncidentPreview };

function grafanaBase(): string {
  const url = process.env.GRAFANA_URL;
  const token = process.env.GRAFANA_SERVICE_ACCOUNT_TOKEN;
  if (!url || !token) throw new Error("GRAFANA_URL and GRAFANA_SERVICE_ACCOUNT_TOKEN are not set");
  return url.replace(/\/$/, "");
}

function headers(): Record<string, string> {
  return {
    Authorization: `Bearer ${process.env.GRAFANA_SERVICE_ACCOUNT_TOKEN ?? ""}`,
    "Content-Type": "application/json",
  };
}

async function irm<T>(method: string, body: unknown): Promise<T> {
  const response = await fetch(`${grafanaBase()}${IRM_PATH}${method}`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 300);
    throw new Error(`Grafana Incident ${method} answered ${response.status}: ${detail}`);
  }
  return (await response.json()) as T;
}

/** "Airlock needs a human: control unavailable on nimbus-clean-clip" to its motive and asset id. */
export function parseIncidentTitle(title: string): { motive: string | null; assetId: string | null } {
  if (!title.startsWith(TITLE_PREFIX)) return { motive: null, assetId: null };
  const rest = title.slice(TITLE_PREFIX.length);
  const split = rest.lastIndexOf(" on ");
  if (split === -1) return { motive: rest, assetId: null };
  return { motive: rest.slice(0, split), assetId: rest.slice(split + 4) };
}

type RawPreview = {
  incidentID: string;
  title: string;
  status: string;
  severityLabel?: string;
  isDrill?: boolean;
  createdTime?: string;
  closedTime?: string;
  slug?: string;
};

function incidentUrl(id: string, slug?: string): string {
  return `${grafanaBase()}/a/grafana-irm-app/incidents/${id}${slug ? `/${slug}` : ""}`;
}

function toPreview(raw: RawPreview): IncidentPreview {
  const { motive, assetId } = parseIncidentTitle(raw.title ?? "");
  return {
    id: String(raw.incidentID),
    title: raw.title ?? "",
    status: raw.status ?? "unknown",
    severity: raw.severityLabel ?? "",
    isDrill: Boolean(raw.isDrill),
    createdAt: raw.createdTime ?? "",
    closedAt: raw.closedTime ? raw.closedTime : null,
    motive,
    assetId,
    url: incidentUrl(String(raw.incidentID), raw.slug),
  };
}

/** The open Airlock incidents, newest first, drills included (the free stack opens them as drills). */
export async function queryOpenIncidents(): Promise<IncidentPreview[]> {
  const payload = await irm<{ incidentPreviews?: RawPreview[] }>("IncidentsService.QueryIncidentPreviews", {
    query: { queryString: "status:active", limit: PREVIEW_LIMIT, orderDirection: "DESC", orderField: "createdTime" },
    includeCustomFieldValues: false,
  });
  return (payload.incidentPreviews ?? [])
    .filter((raw) => typeof raw.title === "string" && raw.title.startsWith("Airlock"))
    .map(toPreview);
}

type RawIncident = RawPreview & {
  labels?: Array<{ key: string; label: string }>;
  summary?: string;
  durationSeconds?: number;
};

export async function getIncident(id: string): Promise<IncidentDetail> {
  const payload = await irm<{ incident?: RawIncident } | RawIncident>("IncidentsService.GetIncident", { incidentID: id });
  const raw = ("incident" in payload && payload.incident ? payload.incident : payload) as RawIncident;
  return {
    ...toPreview(raw),
    labels: (raw.labels ?? []).map((l) => ({ key: l.key, label: l.label })),
    summary: raw.summary ?? "",
    durationSeconds: typeof raw.durationSeconds === "number" ? raw.durationSeconds : null,
  };
}

/** Closes the incident. Returns the status Grafana reports afterwards. */
export async function resolveIncident(id: string): Promise<{ status: string }> {
  const payload = await irm<{ incident?: { status?: string }; status?: string }>("IncidentsService.UpdateStatus", {
    incidentID: id,
    status: "resolved",
  });
  const status = payload.incident?.status ?? payload.status ?? "resolved";
  return { status };
}

/** One annotation on the Airlock dashboard, tagged so the dashboard and the record can find it. */
export async function createAnnotation(text: string, tags: string[]): Promise<{ id: number | null }> {
  const response = await fetch(`${grafanaBase()}/api/annotations`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      dashboardUID: process.env.AIRLOCK_DASHBOARD_UID || "airlock-gates",
      time: Date.now(),
      tags,
      text: text.slice(0, 1000),
    }),
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 300);
    throw new Error(`Grafana annotations answered ${response.status}: ${detail}`);
  }
  const payload = (await response.json()) as { id?: number };
  return { id: typeof payload.id === "number" ? payload.id : null };
}
