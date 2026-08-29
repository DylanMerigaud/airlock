"use client";

import * as React from "react";
import { Wordmark } from "@/components/wordmark";
import { AssetPicker } from "@/components/asset-picker";
import { GateColumn, type HealthView } from "@/components/gate-column";
import { Timeline } from "@/components/timeline";
import { VerdictCard } from "@/components/verdict-card";
import { StatTiles, type StatsView } from "@/components/stat-tiles";
import { SpecStrip } from "@/components/spec-strip";
import { BlockQueue } from "@/components/block-queue";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TooltipProvider } from "@/components/ui/tooltip";
import { escalationLine, useRun } from "@/lib/use-run";
import { loadQueue, saveQueue, type BlockEntry } from "@/lib/block-queue";
import { labelForTarget } from "@/lib/assets";
import type { GateName } from "@/lib/events";

export type ShellProps = {
  dashboardUrl: string;
  environment: string;
  mock: boolean;
};

function EnvBadge({ environment, mock }: { environment: string; mock: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-[2px] border border-line bg-panel px-2.5 py-1.5">
      <span className="h-[6px] w-[6px] rotate-45 bg-pass" aria-hidden="true" />
      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-dim">
        {environment}
      </span>
      {mock && (
        <span className="rounded-[2px] border border-amber/40 bg-amber-shade px-1.5 py-[2px] font-mono text-[9px] uppercase tracking-[0.14em] text-amber">
          mock
        </span>
      )}
    </span>
  );
}

export function ConsoleShell({ dashboardUrl, environment, mock }: ShellProps) {
  const { state, start, retry, busy } = useRun();
  const [target, setTarget] = React.useState<string>("crest");
  const [tab, setTab] = React.useState("review");
  const [reviewed, setReviewed] = React.useState(false);
  const [queue, setQueue] = React.useState<BlockEntry[]>([]);
  // Per run, and kept between runs until the reviewer switches it back off.
  const [muted, setMuted] = React.useState<GateName[]>([]);

  const [health, setHealth] = React.useState<HealthView | null>(null);
  const [healthLoading, setHealthLoading] = React.useState(true);
  const [stats, setStats] = React.useState<StatsView | null>(null);
  const [statsLoading, setStatsLoading] = React.useState(true);

  React.useEffect(() => {
    setQueue(loadQueue());
  }, []);

  const refreshInstruments = React.useCallback(async () => {
    setHealthLoading(true);
    setStatsLoading(true);
    await Promise.all([
      fetch("/api/health", { cache: "no-store" })
        .then((r) => r.json() as Promise<HealthView>)
        .then((payload) => setHealth(payload))
        .catch((error: unknown) =>
          setHealth({
            ok: false,
            mock,
            gates: [],
            error: error instanceof Error ? error.message : "the health route did not answer",
          }),
        )
        .finally(() => setHealthLoading(false)),
      fetch("/api/stats", { cache: "no-store" })
        .then((r) => r.json() as Promise<StatsView>)
        .then((payload) => setStats(payload))
        .catch((error: unknown) =>
          setStats({
            ok: false,
            mock,
            checked_7d: null,
            passed_7d: null,
            blocked_7d: null,
            incidents_7d: null,
            gates_calibrated: null,
            gates_total: 4,
            error: error instanceof Error ? error.message : "the stats route did not answer",
          }),
        )
        .finally(() => setStatsLoading(false)),
    ]);
  }, [mock]);

  React.useEffect(() => {
    void refreshInstruments();
  }, [refreshInstruments]);

  const recorded = React.useRef<number | null>(null);
  React.useEffect(() => {
    if (state.phase !== "settled") return;
    void refreshInstruments();
    const verdict = state.verdict;
    const runKey = state.startedAt;
    if (!verdict || verdict.status === "PASS" || runKey === null) return;
    if (recorded.current === runKey) return;
    recorded.current = runKey;
    const asset = state.target ?? target;
    const entry: BlockEntry = {
      id: `${runKey}`,
      asset,
      assetLabel: labelForTarget(asset),
      motive: verdict.motive ?? "unspecified motive",
      reason: verdict.reasons?.[0] ?? "No reason returned.",
      at: new Date(runKey).toISOString(),
      needsHuman: Boolean(verdict.needs_human),
    };
    setQueue((prev) => {
      const next = [entry, ...prev.filter((e) => e.id !== entry.id)];
      saveQueue(next);
      return next;
    });
  }, [state.phase, state.verdict, state.startedAt, state.target, target, refreshInstruments]);

  const run = React.useCallback(
    (asset: string) => {
      setReviewed(false);
      setTab("review");
      setTarget(asset);
      start(asset, muted);
    },
    [start, muted],
  );

  const toggleMute = React.useCallback((gate: GateName) => {
    setMuted((prev) => (prev.includes(gate) ? prev.filter((g) => g !== gate) : [...prev, gate]));
  }, []);

  const escalation = state.escalation
    ? escalationLine(state.escalation)
    : state.phase === "idle"
      ? "Opens an incident only when a human has to arbitrate."
      : "Waiting for the verdict.";

  return (
    <TooltipProvider delayDuration={200}>
      <div className="relative z-10 min-h-screen">
        <header className="sticky top-0 z-40 border-b border-line bg-void/92 backdrop-blur-md">
          <div className="mx-auto w-full max-w-[1600px] px-5">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-3 pt-3">
              <Wordmark />
              <span className="hidden h-8 w-px bg-line md:block" aria-hidden="true" />
              <Tabs value={tab} onValueChange={setTab} className="-mb-px">
                <TabsList className="border-b-0">
                  <TabsTrigger value="review">Review</TabsTrigger>
                  <TabsTrigger value="queue">
                    Block queue
                    {queue.length > 0 && (
                      <span className="ml-2 rounded-[2px] border border-block-deep/45 bg-block-shade px-1.5 py-[2px] text-[9px] text-block">
                        {queue.length}
                      </span>
                    )}
                  </TabsTrigger>
                </TabsList>
              </Tabs>
              <div className="ml-auto flex items-center gap-3">
                <EnvBadge environment={environment} mock={mock} />
                <Button
                  variant="accent"
                  size="lg"
                  disabled={busy}
                  onClick={() => run(target)}
                  aria-busy={busy}
                >
                  {busy && (
                    <span
                      className="h-[6px] w-[6px] rotate-45 bg-void lamp-live"
                      aria-hidden="true"
                    />
                  )}
                  Run airlock
                </Button>
              </div>
            </div>

            <div className="border-t border-line-soft py-2.5">
              <AssetPicker target={target} onSelect={setTarget} disabled={busy} />
            </div>
          </div>
        </header>

        <Tabs value={tab} onValueChange={setTab}>
          <main className="mx-auto w-full max-w-[1600px] px-5 pb-14 pt-5">
            <TabsContent value="review" className="space-y-4">
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-[300px_minmax(0,1fr)_350px] 2xl:grid-cols-[340px_minmax(0,1fr)_400px]">
                <section id="pipeline" aria-label="Gates, in pipeline order">
                  <h2 className="label-micro mb-3 text-ink-faint">Pipeline</h2>
                  <GateColumn
                    gates={state.gates}
                    verdictStatus={state.verdictStatus}
                    escalationStatus={state.escalationStatus}
                    escalationLine={escalation}
                    health={health}
                    loading={healthLoading}
                    mute={muted}
                    onToggleMute={toggleMute}
                    muteDisabled={busy}
                  />
                </section>

                <section aria-label="Event timeline of the current run" className="min-w-0">
                  <h2 className="label-micro mb-3 text-ink-faint">
                    Current run
                    {state.target && (
                      <span className="ml-2 normal-case tracking-normal text-ink-dim">
                        {labelForTarget(state.target)}
                      </span>
                    )}
                  </h2>
                  <Timeline
                    state={state}
                    dashboardUrl={dashboardUrl}
                    onRetry={() => retry(muted)}
                  />
                </section>

                <section aria-label="Verdict" className="min-w-0">
                  <h2 className="label-micro mb-3 text-ink-faint">Decision</h2>
                  <div className="lg:sticky lg:top-[136px]">
                    <VerdictCard
                      state={state}
                      dashboardUrl={dashboardUrl}
                      reviewed={reviewed}
                      onMarkReviewed={() => setReviewed(true)}
                    />
                  </div>
                </section>
              </div>

              <StatTiles stats={stats} loading={statsLoading} />
              <SpecStrip lastRunMs={state.elapsedMs} />
            </TabsContent>

            <TabsContent value="queue" className="space-y-4">
              <BlockQueue entries={queue} onRerun={run} busy={busy} />
              <Panel>
                <PanelHeader>
                  <PanelTitle>How this queue works</PanelTitle>
                </PanelHeader>
                <PanelBody>
                  <p className="max-w-[80ch] text-[12.5px] leading-[1.6] text-ink-dim">
                    Every run of this browser session that ended BLOCK is kept in local storage, so
                    a reviewer can leave the page and come back to the same worklist. Re-run sends
                    the same asset through the airlock again, which is how a reviewer confirms that
                    a block caused by a degraded control clears once the control is healthy.
                  </p>
                </PanelBody>
              </Panel>
            </TabsContent>
          </main>
        </Tabs>
      </div>
    </TooltipProvider>
  );
}
