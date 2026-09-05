"use client";

import type { RunState } from "@/lib/use-run";

/**
 * The last settled run of this tab, kept in sessionStorage keyed by its
 * startedAt, so a reviewer who follows the Grafana link and comes back finds
 * the same events and verdict rather than an empty desk. Session scoped: a new
 * tab starts clean, and nothing is kept from a run that did not settle.
 */
const KEY = "airlock.console.last-run.v1";

type Stored = { key: number; run: RunState };

export function saveLastRun(state: RunState) {
  if (typeof window === "undefined") return;
  if (state.phase !== "settled" || state.startedAt === null) return;
  try {
    const stored: Stored = { key: state.startedAt, run: { ...state, restored: false } };
    window.sessionStorage.setItem(KEY, JSON.stringify(stored));
  } catch {
    // A full or blocked sessionStorage costs the restore, nothing else.
  }
}

export function loadLastRun(): RunState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Stored>;
    const run = parsed.run;
    if (!run || run.phase !== "settled" || typeof parsed.key !== "number") return null;
    if (run.startedAt !== parsed.key) return null;
    return { ...run, restored: true };
  } catch {
    return null;
  }
}

/** Forgets the stored run: the reviewer moved to another asset and the old verdict must not come back. */
export function clearLastRun() {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // Nothing to forget, or storage blocked: either way the desk is clean.
  }
}
