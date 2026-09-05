"use client";

import * as React from "react";

type TraceSpan = {
  spanId: string;
  parentSpanId: string | null;
  name: string;
  scope: string;
  startNs: number;
  durationMs: number;
  status: "OK" | "ERROR" | "UNSET";
  attributes: Record<string, string | number | boolean>;
};

type TracePayload = {
  ok: boolean;
  traceId: string;
  spans: TraceSpan[];
  serviceName: string | null;
  error: string | null;
};

/** Depth-first order, parent before children, by start time within a parent: a readable span tree
 *  from a flat list with no library. */
function orderedSpans(spans: TraceSpan[]): { span: TraceSpan; depth: number }[] {
  const byParent = new Map<string | null, TraceSpan[]>();
  for (const s of spans) {
    const key = s.parentSpanId && spans.some((p) => p.spanId === s.parentSpanId) ? s.parentSpanId : null;
    byParent.set(key, [...(byParent.get(key) ?? []), s]);
  }
  const out: { span: TraceSpan; depth: number }[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const s of byParent.get(parent) ?? []) {
      out.push({ span: s, depth });
      walk(s.spanId, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

/**
 * The Tempo trace of one run, fetched through the console's own `/api/trace/[id]` (the server's
 * Grafana credentials, no login needed): the partner mission's "correlate with a trace" step,
 * readable by a judge who cannot open Grafana Explore (third panel, 2026-09-05).
 */
export function TraceSpans({ traceId, exploreUrl }: { traceId: string; exploreUrl?: string }) {
  const [payload, setPayload] = React.useState<TracePayload | null>(null);
  const [open, setOpen] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    setPayload(null);
    fetch(`/api/trace/${traceId}`, { cache: "no-store" })
      .then((r) => r.json() as Promise<TracePayload>)
      .then((p) => {
        if (!cancelled) setPayload(p);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setPayload({ ok: false, traceId, spans: [], serviceName: null, error: error instanceof Error ? error.message : String(error) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [traceId]);

  if (!payload) {
    return <p className="px-3 py-2 text-[12px] text-ink-soft">Reading the trace from Tempo.</p>;
  }
  if (!payload.ok || payload.spans.length === 0) {
    return (
      <div className="px-3 py-2 text-[12px] text-ink-soft">
        <p>{payload.error ?? "Tempo returned no spans for this trace."}</p>
        {exploreUrl && (
          <a href={exploreUrl} target="_blank" rel="noopener noreferrer" className="text-accent underline underline-offset-[3px]">
            Open in Grafana Explore instead
          </a>
        )}
      </div>
    );
  }
  const rows = orderedSpans(payload.spans);
  return (
    <div className="px-3 py-2">
      <p className="mb-1.5 font-mono text-[10.5px] text-ink-soft">
        {payload.serviceName ?? "airlock"} &middot; {payload.spans.length} span{payload.spans.length === 1 ? "" : "s"} &middot; trace {traceId.slice(0, 12)}
      </p>
      <ul className="space-y-0.5">
        {rows.map(({ span, depth }) => (
          <li key={span.spanId}>
            <button
              type="button"
              onClick={() => setOpen(open === span.spanId ? null : span.spanId)}
              className="flex w-full items-baseline gap-2 rounded px-1 py-0.5 text-left hover:bg-sunk"
              style={{ paddingLeft: `${depth * 14 + 4}px` }}
            >
              <span
                aria-hidden
                className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
                  span.status === "ERROR" ? "bg-block" : span.status === "OK" ? "bg-pass" : "bg-ink-soft"
                }`}
              />
              <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-ink">{span.name}</span>
              <span className="shrink-0 font-mono text-[10.5px] text-ink-soft">{span.durationMs} ms</span>
            </button>
            {open === span.spanId && Object.keys(span.attributes).length > 0 && (
              <dl className="ml-4 mt-0.5 grid grid-cols-[max-content_1fr] gap-x-2 gap-y-0.5 rounded bg-sunk px-2 py-1.5 font-mono text-[10.5px]">
                {Object.entries(span.attributes).map(([k, v]) => (
                  <React.Fragment key={k}>
                    <dt className="text-ink-soft">{k}</dt>
                    <dd className="truncate text-ink">{String(v)}</dd>
                  </React.Fragment>
                ))}
              </dl>
            )}
          </li>
        ))}
      </ul>
      {exploreUrl && (
        <a href={exploreUrl} target="_blank" rel="noopener noreferrer" className="mt-1.5 inline-block text-[11px] text-accent underline underline-offset-[3px]">
          Open in Grafana Explore
        </a>
      )}
    </div>
  );
}
