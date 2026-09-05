"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { BlockEntry } from "@/lib/block-queue";
import { ownerLabel, type IncidentPreview } from "@/lib/incident-types";

function stamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toISOString().replace("T", " ").slice(0, 19) + "Z";
}

function motiveTone(motive: string | null): "amber" | "block" {
  return motive === "control unavailable" || motive === "uncalibrated control" ? "amber" : "block";
}

const HEAD = "label-micro px-3 py-2 text-ink-soft";

const NO_OWNER_LABEL_HELP =
  "This incident carries no owner label: it was opened before the escalation agent labelled owners. A run that joins it says who owns it in its Record.";

const OWNER_NOT_READ_HELP =
  "The labels of this incident were not read on this refresh (beyond the 20 rows read per refresh, or Grafana did not answer for it).";

/** Who the incident is routed to, in words; the session's own escalation fills in an unlabelled incident it joined. */
export type RunOwner = { incidentId: string; owner: string };

function OwnerCell({ incident, runOwner }: { incident: IncidentPreview; runOwner: RunOwner | null }) {
  if (incident.owner) {
    return <span className="block text-[12.5px] leading-[1.4] text-ink">{ownerLabel(incident.owner)}</span>;
  }
  if (runOwner && runOwner.incidentId === incident.id) {
    return (
      <>
        <span className="block text-[12.5px] leading-[1.4] text-ink">{ownerLabel(runOwner.owner)}</span>
        <span className="mt-0.5 block font-mono text-[10px] text-ink-soft" title={NO_OWNER_LABEL_HELP}>
          from this run&apos;s escalation, no label on the incident
        </span>
      </>
    );
  }
  return (
    <span
      className="block text-[12px] leading-[1.4] text-ink-soft"
      title={incident.ownerRead ? NO_OWNER_LABEL_HELP : OWNER_NOT_READ_HELP}
    >
      {incident.ownerRead ? "no owner label" : "owner not read"}
    </span>
  );
}

/**
 * The open Airlock incidents in Grafana: the queue a reviewer works through.
 * Every one was opened (or joined) by the escalation agent; resolving one from
 * the Record removes it here on the next refresh. The Owner column is the
 * escalation's `owner` label read back from Grafana, in words.
 */
export function IncidentQueue({
  incidents,
  onRerun,
  onResolve,
  rerunTarget,
  runOwner,
  busy,
}: {
  incidents: IncidentPreview[];
  onRerun: (asset: string) => void;
  /** Resolves the incident through the console's route (Grafana Incident UpdateStatus plus a reviewed annotation). */
  onResolve: (incident: IncidentPreview) => Promise<void>;
  /** The console target (preset id or gs:// URI) for an incident's asset id, when the console knows it. */
  rerunTarget: (assetId: string | null) => string | null;
  /** The incident the last run of this session opened or joined, and the owner it routed it to. */
  runOwner: RunOwner | null;
  busy: boolean;
}) {
  const [resolving, setResolving] = React.useState<string | null>(null);
  const [resolveError, setResolveError] = React.useState<{ id: string; message: string } | null>(null);
  const resolve = async (incident: IncidentPreview) => {
    setResolving(incident.id);
    setResolveError(null);
    try {
      await onResolve(incident);
    } catch (error) {
      // The route can refuse (a rate limit, a non-Airlock title) or Grafana can answer with an error;
      // a silent failure here would look like the click did nothing (found live, 2026-09-05).
      setResolveError({ id: incident.id, message: error instanceof Error ? error.message : String(error) });
    } finally {
      setResolving(null);
    }
  };
  if (incidents.length === 0) {
    return (
      <div className="px-6 py-12 text-center">
        <p className="mx-auto max-w-[52ch] text-[13px] leading-[1.55] text-ink-soft">
          No open Airlock incident in Grafana. Every BLOCK that needs a human opens one (or joins the
          open one for the same asset and motive); marking a run reviewed resolves it.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[820px] border-collapse text-left">
        <caption className="sr-only">Open Airlock incidents in Grafana</caption>
        <thead>
          <tr className="border-b border-line">
            <th scope="col" className={HEAD}>
              Incident
            </th>
            <th scope="col" className={HEAD}>
              Asset
            </th>
            <th scope="col" className={HEAD}>
              Motive
            </th>
            <th scope="col" className={HEAD}>
              Owner
            </th>
            <th scope="col" className={HEAD}>
              Opened
            </th>
            <th scope="col" className={`${HEAD} text-right`}>
              Action
            </th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((incident) => {
            const target = rerunTarget(incident.assetId);
            return (
              <tr key={incident.id} className="border-b border-line align-top last:border-b-0">
                <td className="px-3 py-2.5">
                  <a
                    href={incident.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[13px] leading-[1.4] text-accent underline underline-offset-[3px]"
                  >
                    incident {incident.id}
                  </a>
                  <span className="mt-0.5 block font-mono text-[10px] text-ink-soft">
                    {incident.severity ? incident.severity.toLowerCase() : "severity unknown"}
                    {incident.isDrill ? ", drill" : ""}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  <span className="block font-mono text-[11px] leading-[1.4] text-ink">
                    {incident.assetId ?? incident.title}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  {incident.motive ? (
                    <Badge tone={motiveTone(incident.motive)} size="xs" className="normal-case tracking-[0.02em]">
                      {incident.motive}
                    </Badge>
                  ) : (
                    <span className="text-[12px] text-ink-soft">{incident.title}</span>
                  )}
                  <span className="mt-1 block font-mono text-[10px] uppercase tracking-[0.07em] text-warn">
                    needs a human
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  <OwnerCell incident={incident} runOwner={runOwner} />
                </td>
                <td className="tabular whitespace-nowrap px-3 py-2.5 font-mono text-[10.5px] text-ink-soft">
                  {stamp(incident.createdAt)}
                </td>
                <td className="px-3 py-2.5 text-right">
                  <div className="flex flex-wrap justify-end gap-1.5">
                    {target ? (
                      <Button variant="outline" size="sm" disabled={busy} onClick={() => onRerun(target)}>
                        Re-run
                      </Button>
                    ) : (
                      <span className="self-center text-[11px] text-ink-soft">asset not preloaded here</span>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy || resolving !== null}
                      onClick={() => void resolve(incident)}
                      aria-label={`Resolve incident ${incident.id} as reviewed by a human`}
                    >
                      {resolving === incident.id ? "Resolving" : "Resolve"}
                    </Button>
                  </div>
                  {resolveError?.id === incident.id && (
                    <p role="alert" className="mt-1 max-w-[28ch] text-right text-[11px] leading-[1.4] text-warn">
                      {resolveError.message}
                    </p>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** The runs of this browser that ended BLOCK: the offline fallback when Grafana does not answer. */
export function BlockQueue({
  entries,
  onRerun,
  busy,
}: {
  entries: BlockEntry[];
  onRerun: (asset: string) => void;
  busy: boolean;
}) {
  if (entries.length === 0) {
    return (
      <div className="px-6 py-12 text-center">
        <p className="mx-auto max-w-[52ch] text-[13px] leading-[1.55] text-ink-soft">
          Nothing blocked yet in this browser. Every run that ends BLOCK lands here with its motive
          and its first reason, so a reviewer can work through the queue.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse text-left">
        <caption className="sr-only">Runs of this browser session that ended in a block</caption>
        <thead>
          <tr className="border-b border-line">
            <th scope="col" className={HEAD}>
              Asset
            </th>
            <th scope="col" className={HEAD}>
              Motive
            </th>
            <th scope="col" className={HEAD}>
              First reason
            </th>
            <th scope="col" className={HEAD}>
              When
            </th>
            <th scope="col" className={`${HEAD} text-right`}>
              Action
            </th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.id} className="border-b border-line align-top last:border-b-0">
              <td className="px-3 py-2.5">
                <span className="block text-[13px] leading-[1.4] text-ink">{entry.assetLabel}</span>
                <span className="mt-0.5 block font-mono text-[10px] text-ink-soft">{entry.asset}</span>
              </td>
              <td className="px-3 py-2.5">
                <Badge tone={motiveTone(entry.motive)} size="xs" className="normal-case tracking-[0.02em]">
                  {entry.motive}
                </Badge>
                {entry.needsHuman && (
                  <span className="mt-1 block font-mono text-[10px] uppercase tracking-[0.07em] text-warn">
                    needs a human
                  </span>
                )}
              </td>
              <td className="max-w-[380px] px-3 py-2.5 text-[12.5px] leading-[1.45] text-ink">{entry.reason}</td>
              <td className="tabular whitespace-nowrap px-3 py-2.5 font-mono text-[10.5px] text-ink-soft">
                {stamp(entry.at)}
              </td>
              <td className="px-3 py-2.5 text-right">
                <Button variant="outline" size="sm" disabled={busy} onClick={() => onRerun(entry.asset)}>
                  Re-run
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
