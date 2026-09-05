"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { IncidentPreview, IncidentsPayload } from "@/lib/incident-types";

export type IncidentsView = {
  /** The open Airlock incidents in Grafana, newest first; null before the first answer. */
  incidents: IncidentPreview[] | null;
  /** Grafana did not answer the last time it was asked; the queue falls back to this browser's list. */
  error: string | null;
  mock: boolean;
  loading: boolean;
  readAt: string | null;
  refresh: () => Promise<void>;
};

/**
 * The BLOCK queue is Grafana's list of open incidents, read through
 * /api/incidents: one refresh on mount, one per settled run, one per resolve.
 * While the route answers ok: false the last good list stays on screen and the
 * component says so.
 */
export function useIncidents(): IncidentsView {
  const [incidents, setIncidents] = useState<IncidentPreview[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mock, setMock] = useState(false);
  const [loading, setLoading] = useState(true);
  const [readAt, setReadAt] = useState<string | null>(null);
  const inflight = useRef<Promise<void> | null>(null);

  const refresh = useCallback(async () => {
    if (inflight.current) return inflight.current;
    const work = (async () => {
      try {
        const response = await fetch("/api/incidents", { cache: "no-store" });
        const payload = (await response.json()) as IncidentsPayload;
        setMock(payload.mock);
        setReadAt(payload.read_at);
        if (payload.ok) {
          setIncidents(payload.incidents);
          setError(null);
        } else {
          setError(payload.error ?? "Grafana did not answer.");
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "The incidents route did not answer.");
      } finally {
        setLoading(false);
        inflight.current = null;
      }
    })();
    inflight.current = work;
    return work;
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { incidents, error, mock, loading, readAt, refresh };
}
