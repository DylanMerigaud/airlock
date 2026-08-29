import "server-only";

/**
 * The console asks Grafana the same questions the verdict agent asks through
 * MCP, over the plain HTTP datasource proxy. Same PromQL, same instance.
 */

export type InstantQuery = { refId: string; expr: string };
export type InstantResult = { value: number | null; error?: string };

export function grafanaConfigured(): boolean {
  return Boolean(process.env.GRAFANA_URL && process.env.GRAFANA_SERVICE_ACCOUNT_TOKEN);
}

export function isMock(): boolean {
  return process.env.AIRLOCK_MOCK === "1";
}

export async function grafanaInstant(queries: InstantQuery[]): Promise<Record<string, InstantResult>> {
  const url = process.env.GRAFANA_URL;
  const token = process.env.GRAFANA_SERVICE_ACCOUNT_TOKEN;
  const uid = process.env.GRAFANA_PROM_UID || "grafanacloud-prom";
  if (!url || !token) {
    throw new Error("GRAFANA_URL and GRAFANA_SERVICE_ACCOUNT_TOKEN are not set");
  }

  const now = Date.now();
  const body = {
    queries: queries.map((q) => ({
      refId: q.refId,
      datasource: { uid },
      expr: q.expr,
      instant: true,
      intervalMs: 60000,
      maxDataPoints: 1,
    })),
    from: String(now - 60 * 60 * 1000),
    to: String(now),
  };

  const response = await fetch(`${url.replace(/\/$/, "")}/api/ds/query`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
  });

  if (!response.ok) {
    const detail = (await response.text()).slice(0, 200);
    throw new Error(`Grafana answered ${response.status}: ${detail}`);
  }

  const payload = (await response.json()) as {
    results?: Record<string, { frames?: Array<{ data?: { values?: unknown[][] } }>; error?: string }>;
  };

  const out: Record<string, InstantResult> = {};
  for (const query of queries) {
    const slot = payload.results?.[query.refId];
    if (!slot) {
      out[query.refId] = { value: null, error: "no result for this query" };
      continue;
    }
    if (slot.error) {
      out[query.refId] = { value: null, error: slot.error };
      continue;
    }
    const values = slot.frames?.[0]?.data?.values;
    const raw = values?.[1]?.[0];
    out[query.refId] = { value: typeof raw === "number" && Number.isFinite(raw) ? raw : null };
  }
  return out;
}

/** A tiny server-side cache: the reviewer refreshes, Grafana does not care. */
export function cached<T>(ttlMs: number) {
  let at = 0;
  let payload: T | null = null;
  let inflight: Promise<T> | null = null;

  return async function get(load: () => Promise<T>): Promise<T> {
    const now = Date.now();
    if (payload !== null && now - at < ttlMs) return payload;
    if (inflight) return inflight;
    inflight = load()
      .then((value) => {
        payload = value;
        at = Date.now();
        return value;
      })
      .finally(() => {
        inflight = null;
      });
    return inflight;
  };
}
