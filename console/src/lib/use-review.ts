"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ResolvePayload, ReviewerRole } from "@/lib/review";
import { verdictSummary } from "@/lib/review";
import type { RunState } from "@/lib/use-run";

export type ReviewState =
  | { phase: "idle" }
  | { phase: "pending" }
  | { phase: "done"; result: ResolvePayload }
  | { phase: "failed"; error: string };

export type ReviewHandle = {
  review: ReviewState;
  /** Resolves the run's incident in Grafana and writes the reviewed annotation, signed with the role. */
  submit: (role: ReviewerRole) => Promise<void>;
  reset: () => void;
};

/**
 * The reviewer's decision goes to /api/incident/resolve, which closes the
 * incident through Grafana Incident and writes an annotation tagged reviewed.
 * The state resets when a new run starts, so a review is always about the run
 * on screen.
 */
export function useReview(state: RunState, onResolved?: () => void): ReviewHandle {
  const [review, setReview] = useState<ReviewState>({ phase: "idle" });
  const runKey = useRef<number | null>(state.startedAt);

  useEffect(() => {
    if (state.startedAt !== runKey.current) {
      runKey.current = state.startedAt;
      setReview({ phase: "idle" });
    }
  }, [state.startedAt]);

  const submit = useCallback(
    async (role: ReviewerRole) => {
      const verdict = state.verdict;
      if (!verdict) return;
      setReview({ phase: "pending" });
      try {
        const response = await fetch("/api/incident/resolve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            incidentID: state.escalation?.incident_id ?? null,
            reviewer_role: role,
            summary: verdictSummary(verdict.status, verdict.motive, verdict.asset_id, state.gates.rights.runId ?? undefined),
            asset_id: verdict.asset_id ?? null,
          }),
        });
        const payload = (await response.json()) as ResolvePayload & { error?: string | null };
        if (!response.ok) {
          setReview({ phase: "failed", error: payload.error ?? `The resolve route answered ${response.status}.` });
          return;
        }
        setReview({ phase: "done", result: payload });
        onResolved?.();
      } catch (error) {
        setReview({ phase: "failed", error: error instanceof Error ? error.message : String(error) });
      }
    },
    [state.verdict, state.escalation, state.gates.rights.runId, onResolved],
  );

  const reset = useCallback(() => setReview({ phase: "idle" }), []);

  return { review, submit, reset };
}
