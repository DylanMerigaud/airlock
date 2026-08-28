"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader, PanelTitle } from "@/components/ui/card";
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
  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>Blocked in this session</PanelTitle>
        <span className="tabular font-mono text-[10.5px] text-ink-faint">
          {entries.length} run{entries.length === 1 ? "" : "s"}
        </span>
      </PanelHeader>

      {entries.length === 0 ? (
        <div className="px-8 py-16 text-center">
          <p className="mx-auto max-w-[52ch] text-[13px] leading-[1.6] text-ink-faint">
            Nothing blocked yet in this browser. Every run that ends BLOCK lands here with its
            motive and its first reason, so a reviewer can work through the queue.
          </p>
        </div>
      ) : (
        <table className="w-full border-collapse text-left">
          <caption className="sr-only">
            Runs of this browser session that ended in a block
          </caption>
          <thead>
            <tr className="border-b border-line-soft">
              <th scope="col" className="label-micro px-4 py-2.5 text-ink-faint">
                Asset
              </th>
              <th scope="col" className="label-micro px-4 py-2.5 text-ink-faint">
                Motive
              </th>
              <th scope="col" className="label-micro px-4 py-2.5 text-ink-faint">
                First reason
              </th>
              <th scope="col" className="label-micro px-4 py-2.5 text-ink-faint">
                When
              </th>
              <th scope="col" className="label-micro px-4 py-2.5 text-right text-ink-faint">
                Action
              </th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id} className="border-b border-line-soft last:border-b-0 align-top">
                <td className="px-4 py-3">
                  <span className="block text-[12.5px] leading-[1.4] text-ink">
                    {entry.assetLabel}
                  </span>
                  <span className="mt-1 block font-mono text-[10px] text-ink-faint">
                    {entry.asset}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <Badge
                    tone={
                      entry.motive === "control unavailable" ||
                      entry.motive === "uncalibrated control"
                        ? "amber"
                        : "block"
                    }
                    size="xs"
                    className="normal-case tracking-[0.05em]"
                  >
                    {entry.motive}
                  </Badge>
                  {entry.needsHuman && (
                    <span className="mt-1.5 block font-mono text-[9.5px] uppercase tracking-[0.12em] text-amber">
                      needs a human
                    </span>
                  )}
                </td>
                <td className="max-w-[380px] px-4 py-3 text-[12.5px] leading-[1.5] text-ink-dim">
                  {entry.reason}
                </td>
                <td className="tabular whitespace-nowrap px-4 py-3 font-mono text-[10.5px] text-ink-faint">
                  {stamp(entry.at)}
                </td>
                <td className="px-4 py-3 text-right">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy}
                    onClick={() => onRerun(entry.asset)}
                  >
                    Re-run
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
