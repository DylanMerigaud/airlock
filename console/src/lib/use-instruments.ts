"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { StatsView } from "@/components/stat-tiles";
import { describeOutage, type HealthView, type Outage } from "@/lib/instrument";

/**
 * The Grafana Cloud free stack pauses after idle days and answers 503
 * "Loading" for about two minutes while it wakes. While either route answers
 * ok: false the console retries every 10 s for 3 minutes, then every 60 s,
 * and keeps the last good payload on screen. Nothing polls while all is well:
 * one refresh on mount and one per settled run, as before.
 */
export const RETRY_FAST_MS = 10_000;
export const RETRY_SLOW_MS = 60_000;
export const RETRY_BUDGET_MS = 180_000;

export type Instruments = {
  /** The last good health payload, kept through an outage. */
  health: HealthView | null;
  /** The last good stats payload, kept through an outage. */
  stats: StatsView | null;
  /** No answer of any kind yet. */
  loading: boolean;
  outage: Outage | null;
  refresh: () => Promise<void>;
};

function fallbackHealth(mock: boolean, error: string): HealthView {
  return { ok: false, mock, gates: [], error };
}

function fallbackStats(mock: boolean, error: string): StatsView {
  return {
    ok: false,
    mock,
    checked_7d: null,
    passed_7d: null,
    blocked_7d: null,
    incidents_7d: null,
    gates_calibrated: null,
    gates_total: 4,
    cost_per_check_usd_7d: null,
    error,
  };
}

async function read<T>(url: string, fallback: (error: string) => T): Promise<T> {
  try {
    const response = await fetch(url, { cache: "no-store" });
    return (await response.json()) as T;
  } catch (error: unknown) {
    return fallback(error instanceof Error ? error.message : `${url} did not answer`);
  }
}

export function useInstruments(mock: boolean): Instruments {
  const [health, setHealth] = useState<HealthView | null>(null);
  const [stats, setStats] = useState<StatsView | null>(null);
  const [loading, setLoading] = useState(true);
  const [outage, setOutage] = useState<Outage | null>(null);

  const outageRef = useRef<Outage | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inflight = useRef<Promise<void> | null>(null);
  const alive = useRef(true);
  const refreshRef = useRef<() => Promise<void>>(async () => {});

  const refresh = useCallback(async () => {
    if (inflight.current) return inflight.current;
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }

    const work = (async () => {
      const [h, s] = await Promise.all([
        read<HealthView>("/api/health", (error) => fallbackHealth(mock, error)),
        read<StatsView>("/api/stats", (error) => fallbackStats(mock, error)),
      ]);
      if (!alive.current) return;

      if (h.ok) setHealth(h);
      if (s.ok) setStats(s);
      setLoading(false);

      if (h.ok && s.ok) {
        outageRef.current = null;
        setOutage(null);
        return;
      }

      const raw = (!h.ok ? h.error : s.error) ?? "no answer";
      const since = outageRef.current?.since ?? Date.now();
      const next: Outage = {
        since,
        raw,
        ...describeOutage(raw),
        exhausted: Date.now() - since >= RETRY_BUDGET_MS,
      };
      outageRef.current = next;
      setOutage(next);
      timer.current = setTimeout(
        () => void refreshRef.current(),
        next.exhausted ? RETRY_SLOW_MS : RETRY_FAST_MS,
      );
    })().finally(() => {
      inflight.current = null;
    });

    inflight.current = work;
    return work;
  }, [mock]);

  refreshRef.current = refresh;

  useEffect(() => {
    alive.current = true;
    void refresh();
    return () => {
      alive.current = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [refresh]);

  return { health, stats, loading, outage, refresh };
}
