"use client";

import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatVerdictCostLine, groupRuleIds, readC2pa, type LokiLine } from "@/lib/events";
import { labelForTarget } from "@/lib/assets";
import { REVIEWER_ROLES, type ReviewerRole } from "@/lib/review";
import type { ReviewState } from "@/lib/use-review";
import type { RunState } from "@/lib/use-run";

function clockUtc(ms: number): string {
  const d = new Date(ms);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm} UTC`;
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 12 12"
      width="11"
      height="11"
      aria-hidden="true"
      className={cn("shrink-0 text-ink-soft transition-transform duration-150", open && "rotate-90")}
    >
      <path d="M4 2.5 8 6l-4 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

function lokiStamp(line: LokiLine): string {
  return `${line.time_utc ?? "no timestamp"} ${line.gate ?? ""} ${line.status ?? ""}${line.fault ? ` (fault: ${line.fault})` : ""}`;
}

/** The note without its conclusion line, which is shown on its own. */
function noteBody(note: string, conclusion: string | null | undefined): string {
  if (!conclusion) return note;
  return note
    .split("\n")
    .filter((line) => line.trim().replace(/^[*#\s]+/, "") !== conclusion.trim())
    .join("\n")
    .trim();
}

/**
 * The paperwork the run leaves behind: the rules it cited, what C2PA said, the
 * investigator's note, the annotation and incident it wrote, and the one action
 * a reviewer can take, which closes the incident in Grafana.
 */
export function DecisionRecord({
  state,
  dashboardUrl,
  review,
  onReview,
}: {
  state: RunState;
  dashboardUrl: string;
  review: ReviewState;
  onReview: (role: ReviewerRole) => void;
}) {
  const [rulesOpen, setRulesOpen] = React.useState(false);
  const [role, setRole] = React.useState<ReviewerRole>(REVIEWER_ROLES[0]);
  const verdict = state.verdict;
  const investigation = state.investigation;

  if (!verdict) {
    return (
      <p className="px-3 py-4 text-[13px] leading-[1.5] text-ink-soft">
        Nothing recorded yet. A finished run writes its rules, its C2PA reading, its Grafana
        annotation and any incident here.
      </p>
    );
  }

  const ruleIds = Array.from(
    new Set([
      ...(verdict.rule_ids ?? []),
      ...(verdict.gates ?? [])
        .filter((g) => (verdict.status === "PASS" ? true : g.status !== "PASS"))
        .flatMap((g) => g.rule_ids ?? []),
    ]),
  );
  const groups = groupRuleIds(ruleIds);
  const c2pa = readC2pa(state.gates.provenance.done);
  const escalation = state.escalation;

  const assetLabel = state.target ? labelForTarget(state.target) : null;

  return (
    <div>
      <section className="border-b border-line px-3 py-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="label-micro text-ink-soft">Written to Grafana during the run</h3>
          <span className="font-mono text-[10.5px] text-ink-soft">
            {verdict.annotation_id !== undefined && verdict.annotation_id !== null
              ? `annotation ${verdict.annotation_id}`
              : "no annotation id"}
            {escalation?.incident_id ? `, incident ${escalation.incident_id}` : ""}
          </span>
        </div>
        {(assetLabel || verdict.asset_id) && (
          <p className="mt-1 flex flex-wrap items-baseline gap-x-2 text-[12.5px] leading-[1.45] text-ink">
            {assetLabel && <span>{assetLabel}</span>}
            {verdict.asset_id && (
              <span className="font-mono text-[10.5px] text-ink-soft">{verdict.asset_id}</span>
            )}
          </p>
        )}
        {state.restored && state.startedAt !== null && (
          <p className="mt-1 font-mono text-[10.5px] leading-[1.45] text-ink-soft">
            restored: this run started at {clockUtc(state.startedAt)} and was kept in this tab while
            you were away
          </p>
        )}
      </section>

      {ruleIds.length > 0 && (
        <section className="border-b border-line px-3 py-2">
          <button
            type="button"
            onClick={() => setRulesOpen((value) => !value)}
            aria-expanded={rulesOpen}
            aria-controls="rules-cited"
            className="label-micro flex w-full items-center justify-between gap-2 text-ink-soft transition-colors hover:text-ink"
          >
            Rules cited ({ruleIds.length})
            <Chevron open={rulesOpen} />
          </button>
          {rulesOpen && (
            <div id="rules-cited" className="fade-in mt-2.5 space-y-2">
              {groups.map((group) => (
                <div key={group.source}>
                  <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-soft">
                    {group.source}
                  </p>
                  <ul className="mt-1.5 flex flex-wrap gap-1.5">
                    {group.ids.map((id) => (
                      <li key={id}>
                        <Badge tone="ink" size="xs" className="normal-case tracking-[0.01em]">
                          {id}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {c2pa && (
        <section className="border-b border-line px-3 py-2">
          <h3 className="label-micro text-ink-soft">Provenance</h3>
          <p
            className={cn(
              "mt-1 font-mono text-[11px] leading-[1.5]",
              c2pa.ok ? "text-ink" : "text-block",
            )}
          >
            {c2pa.line}
          </p>
        </section>
      )}

      {(investigation || state.investigationStatus === "RUNNING") && (
        <section className="border-b border-line px-3 py-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="label-micro text-ink-soft">Investigation</h3>
            <span className="font-mono text-[10.5px] text-ink-soft">
              {investigation
                ? `${investigation.model ?? "gemini-2.5-flash"}, ${investigation.tool_calls ?? 0} tool call${
                    investigation.tool_calls === 1 ? "" : "s"
                  } through mcp-grafana`
                : "reading Loki through mcp-grafana"}
            </span>
          </div>
          {investigation ? (
            <>
              {investigation.fallback && (
                <p className="mt-1 text-[12px] leading-[1.45] text-warn">
                  The investigator could not run; what follows is the verdict&apos;s own reason.
                </p>
              )}
              {noteBody(investigation.note, investigation.conclusion) && (
                <p className="mt-1 whitespace-pre-line text-[12.5px] leading-[1.5] text-ink">
                  {noteBody(investigation.note, investigation.conclusion)}
                </p>
              )}
              {investigation.conclusion && (
                <p className="mt-1.5 text-[12.5px] leading-[1.5] text-ink">
                  <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-soft">
                    {investigation.kind}
                  </span>{" "}
                  {investigation.conclusion.replace(/^[A-Z ]+:\**\s*/, "")}
                </p>
              )}
              {(investigation.cited ?? []).length > 0 && (
                <ul className="mt-2 space-y-1">
                  {(investigation.cited ?? []).map((line, index) => (
                    <li key={`${line.time_utc}-${line.gate}-${index}`} className="font-mono text-[10.5px] leading-[1.5] text-ink-soft">
                      <span className="text-ink">{lokiStamp(line)}</span>
                      {line.reason ? `: ${line.reason}` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="mt-1 text-[12.5px] leading-[1.5] text-ink-soft">
              The investigator is reading this run&apos;s Loki lines and the alert rules.
            </p>
          )}
        </section>
      )}

      {verdict.cost && (
        <section className="border-b border-line px-3 py-2">
          <h3 className="label-micro text-ink-soft">Cost</h3>
          <p className="mt-1 font-mono text-[11px] leading-[1.5] text-ink-soft">
            {formatVerdictCostLine(verdict.cost)}
          </p>
        </section>
      )}

      <section className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2">
        <span className="text-[12.5px] leading-[1.45] text-ink-soft">
          The verdict agent wrote the annotation itself.
        </span>
        <a
          href={dashboardUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[12.5px] text-accent underline underline-offset-[3px]"
        >
          Open in Grafana
        </a>
      </section>

      {verdict.needs_human && (
        <section className="px-3 py-2.5">
          {review.phase === "done" && review.result ? (
            <>
              <p className="flex items-center gap-2 text-[13px] text-ink">
                <span className="h-[8px] w-[8px] rounded-[1px] bg-pass" aria-hidden="true" />
                Reviewed by a human ({review.result.reviewer_role}).
              </p>
              <p className="mt-1 font-mono text-[10.5px] leading-[1.5] text-ink-soft">
                {review.result.incident_id
                  ? `incident ${review.result.incident_id} ${review.result.status ?? "not resolved"}`
                  : "no incident to close"}
                {review.result.annotation_id !== null ? `, annotation ${review.result.annotation_id} written` : ", no annotation written"}
                {review.result.mock ? " (mock)" : ""}
              </p>
              {review.result.error && (
                <p className="mt-1 text-[12px] leading-[1.45] text-block">{review.result.error}</p>
              )}
            </>
          ) : (
            <>
              <label className="flex items-center justify-between gap-2 text-[12px] text-ink-soft">
                <span>Signing as</span>
                <select
                  value={role}
                  onChange={(event) => setRole(event.target.value as ReviewerRole)}
                  disabled={review.phase === "pending"}
                  className="h-7 rounded-[2px] border border-line-strong bg-surface px-2 text-[12px] text-ink"
                >
                  {REVIEWER_ROLES.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
              <Button
                variant="outline"
                size="sm"
                onClick={() => onReview(role)}
                disabled={review.phase === "pending"}
                aria-busy={review.phase === "pending"}
                className="mt-2 w-full"
              >
                {review.phase === "pending" ? "Closing the incident in Grafana" : "Mark reviewed by a human"}
              </Button>
              <p className="mt-1.5 text-[12px] leading-[1.45] text-ink-soft">
                {escalation?.incident_id
                  ? `Resolves incident ${escalation.incident_id} in Grafana and writes an annotation tagged reviewed with your role and the verdict.`
                  : "No incident was opened for this run; the review is written as an annotation tagged reviewed."}
              </p>
              {review.phase === "failed" && review.error && (
                <p className="mt-1 text-[12px] leading-[1.45] text-block">{review.error}</p>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
