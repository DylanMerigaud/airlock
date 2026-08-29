"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { BlockEntry } from "@/lib/block-queue";

function stamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toISOString().replace("T", " ").slice(0, 19) + "Z";
}

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
            <th scope="col" className="label-micro px-3 py-2 text-ink-soft">
              Asset
            </th>
            <th scope="col" className="label-micro px-3 py-2 text-ink-soft">
              Motive
            </th>
            <th scope="col" className="label-micro px-3 py-2 text-ink-soft">
              First reason
            </th>
            <th scope="col" className="label-micro px-3 py-2 text-ink-soft">
              When
            </th>
            <th scope="col" className="label-micro px-3 py-2 text-right text-ink-soft">
              Action
            </th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.id} className="border-b border-line align-top last:border-b-0">
              <td className="px-3 py-2.5">
                <span className="block text-[13px] leading-[1.4] text-ink">{entry.assetLabel}</span>
                <span className="mt-0.5 block font-mono text-[10px] text-ink-soft">
                  {entry.asset}
                </span>
              </td>
              <td className="px-3 py-2.5">
                <Badge
                  tone={
                    entry.motive === "control unavailable" ||
                    entry.motive === "uncalibrated control"
                      ? "amber"
                      : "block"
                  }
                  size="xs"
                  className="normal-case tracking-[0.02em]"
                >
                  {entry.motive}
                </Badge>
                {entry.needsHuman && (
                  <span className="mt-1 block font-mono text-[10px] uppercase tracking-[0.07em] text-warn">
                    needs a human
                  </span>
                )}
              </td>
              <td className="max-w-[380px] px-3 py-2.5 text-[12.5px] leading-[1.45] text-ink">
                {entry.reason}
              </td>
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
