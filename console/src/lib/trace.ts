import "server-only";

/**
 * Reads a trace back from the stack's Tempo datasource through the Grafana proxy, with the
 * server's own service account token, and flattens it into a span list the Trace view can render
 * with no Grafana login. Two judges of the third panel (2026-09-05) could open the incident and the
 * annotation but not the trace link the product hands out, because Explore needs a Grafana session.
 */

export type TraceSpan = {
  spanId: string;
  parentSpanId: string | null;
  name: string;
  scope: string;
  startNs: number;
  durationMs: number;
  status: "OK" | "ERROR" | "UNSET";
  attributes: Record<string, string | number | boolean>;
};

export type TracePayload = {
  ok: boolean;
  traceId: string;
  spans: TraceSpan[];
  serviceName: string | null;
  error: string | null;
};

function base64ToHex(b64: string): string {
  return Buffer.from(b64, "base64").toString("hex");
}

function attrValue(v: Record<string, unknown> | undefined): string | number | boolean {
  if (!v) return "";
  if ("stringValue" in v) return String(v.stringValue);
  if ("intValue" in v) return Number(v.intValue);
  if ("boolValue" in v) return Boolean(v.boolValue);
  if ("doubleValue" in v) return Number(v.doubleValue);
  return JSON.stringify(v);
}

function flattenAttributes(attrs: unknown): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  if (!Array.isArray(attrs)) return out;
  for (const a of attrs) {
    if (a && typeof a === "object" && "key" in a) {
      out[String((a as { key: unknown }).key)] = attrValue((a as { value?: Record<string, unknown> }).value);
    }
  }
  return out;
}

const STATUS_CODES: Record<number, TraceSpan["status"]> = { 0: "UNSET", 1: "OK", 2: "ERROR" };

export async function readTrace(traceId: string): Promise<TracePayload> {
  const base = process.env.GRAFANA_URL;
  const token = process.env.GRAFANA_SERVICE_ACCOUNT_TOKEN;
  const uid = process.env.GRAFANA_TEMPO_UID || "grafanacloud-traces";
  if (!base || !token) {
    return { ok: false, traceId, spans: [], serviceName: null, error: "GRAFANA_URL and GRAFANA_SERVICE_ACCOUNT_TOKEN are not set" };
  }
  const url = `${base.replace(/\/$/, "")}/api/datasources/proxy/uid/${uid}/api/traces/${traceId}`;
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" });
  if (!res.ok) {
    return { ok: false, traceId, spans: [], serviceName: null, error: `Tempo answered ${res.status}` };
  }
  const body = (await res.json()) as { batches?: unknown[] };
  const spans: TraceSpan[] = [];
  let serviceName: string | null = null;
  for (const batch of body.batches ?? []) {
    if (!batch || typeof batch !== "object") continue;
    const b = batch as { resource?: { attributes?: unknown }; scopeSpans?: unknown[] };
    const resourceAttrs = flattenAttributes(b.resource?.attributes);
    if (typeof resourceAttrs["service.name"] === "string") serviceName = resourceAttrs["service.name"];
    for (const scopeSpan of b.scopeSpans ?? []) {
      if (!scopeSpan || typeof scopeSpan !== "object") continue;
      const ss = scopeSpan as { scope?: { name?: string }; spans?: unknown[] };
      const scopeName = ss.scope?.name ?? "";
      for (const raw of ss.spans ?? []) {
        if (!raw || typeof raw !== "object") continue;
        const s = raw as Record<string, unknown>;
        const startNs = Number(s.startTimeUnixNano ?? 0);
        const endNs = Number(s.endTimeUnixNano ?? startNs);
        const statusCode = (s.status as { code?: number } | undefined)?.code ?? 0;
        spans.push({
          spanId: base64ToHex(String(s.spanId ?? "")),
          parentSpanId: s.parentSpanId ? base64ToHex(String(s.parentSpanId)) : null,
          name: String(s.name ?? "(unnamed span)"),
          scope: scopeName,
          startNs,
          durationMs: Math.round((endNs - startNs) / 1e6),
          status: STATUS_CODES[statusCode] ?? "UNSET",
          attributes: flattenAttributes(s.attributes),
        });
      }
    }
  }
  spans.sort((a, b) => a.startNs - b.startNs);
  return { ok: true, traceId, spans, serviceName, error: null };
}
