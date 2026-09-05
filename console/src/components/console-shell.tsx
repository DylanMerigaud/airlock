"use client";

import * as React from "react";
import { Wordmark } from "@/components/wordmark";
import { AssetStrip } from "@/components/asset-strip";
import { ChecksList, VerdictSummary } from "@/components/checks-panel";
import { DecisionRecord } from "@/components/decision-record";
import { FindingsThread } from "@/components/findings-thread";
import { Stage, type StageAsset } from "@/components/stage";
import { Timeline } from "@/components/timeline";
import { StatTiles } from "@/components/stat-tiles";
import { SpecStrip } from "@/components/spec-strip";
import { BlockQueue, IncidentQueue } from "@/components/block-queue";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/card";
import { SegmentTrigger, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useRun } from "@/lib/use-run";
import { useInstruments } from "@/lib/use-instruments";
import { useIncidents } from "@/lib/use-incidents";
import { useReview } from "@/lib/use-review";
import { buildFindings, verdictNotes } from "@/lib/findings";
import { collectMarkers } from "@/lib/timecodes";
import { loadQueue, saveQueue, type BlockEntry } from "@/lib/block-queue";
import { assetIdFor, labelForTarget, presetById, PRESET_ASSETS } from "@/lib/assets";
import type { FaultMap, GateName } from "@/lib/events";

const SOURCES_LINE =
  "Every clip is read against the Nimbus brand book (charter.yaml), the rights registry, 16 CFR 255 with two ASA rulings, and its C2PA manifest.";

export type ShellProps = {
  dashboardUrl: string;
  environment: string;
  mock: boolean;
};

function EnvBadge({ environment, mock }: { environment: string; mock: boolean }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-[7px] w-[7px] rounded-[1px] bg-pass" aria-hidden="true" />
      <span className="hidden font-mono text-[11px] text-ink-soft lg:inline">{environment}</span>
      {mock && (
        <span className="rounded-[2px] border border-line bg-sunk px-1.5 py-[2px] font-mono text-[10px] uppercase tracking-[0.08em] text-ink-soft">
          mock
        </span>
      )}
    </span>
  );
}

export function ConsoleShell({ dashboardUrl, environment, mock }: ShellProps) {
  const { state, start, retry, busy } = useRun();
  const [target, setTarget] = React.useState<string>("crest");
  const [upload, setUpload] = React.useState<{ name: string; objectUrl: string } | null>(null);
  const [tab, setTab] = React.useState("review");
  // What the right column is reading. The clip never leaves the screen for it.
  const [segment, setSegment] = React.useState("checks");
  // The runs of this browser that ended BLOCK: the offline fallback of the queue.
  const [queue, setQueue] = React.useState<BlockEntry[]>([]);
  // Per run, and kept between runs until the reviewer switches it back off.
  const [muted, setMuted] = React.useState<GateName[]>([]);
  // The faults to inject, gate by gate; travels in the run body beside mute.
  const [faults, setFaults] = React.useState<FaultMap>({});

  // Grafana's readings: one refresh on mount, one per settled run, and its own
  // retries while a route answers ok: false (a paused Grafana Cloud stack waking).
  const instruments = useInstruments(mock);
  const refreshInstruments = instruments.refresh;
  // The queue: Grafana's open incidents, refreshed per settled run and per resolve.
  const incidentsView = useIncidents();
  const refreshIncidents = incidentsView.refresh;
  const { review, submit: submitReview } = useReview(state, refreshIncidents);

  const videoRef = React.useRef<HTMLVideoElement | null>(null);
  const [clipReady, setClipReady] = React.useState(false);
  const [stageNote, setStageNote] = React.useState<string | null>(null);
  const [activeSecond, setActiveSecond] = React.useState<number | null>(null);
  const [hoverSecond, setHoverSecond] = React.useState<number | null>(null);

  React.useEffect(() => {
    setQueue(loadQueue());
  }, []);

  // A run restored from this tab's session puts its clip back on the stage.
  React.useEffect(() => {
    if (state.restored && state.target) setTarget(state.target);
  }, [state.restored, state.target]);

  const recorded = React.useRef<number | null>(null);
  React.useEffect(() => {
    if (state.phase !== "settled") return;
    // A restored run already refreshed the instruments and queued itself when it landed.
    if (state.restored) return;
    void refreshInstruments();
    void refreshIncidents();
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
  }, [
    state.phase,
    state.restored,
    state.verdict,
    state.startedAt,
    state.target,
    target,
    refreshInstruments,
    refreshIncidents,
  ]);

  // An incident names the pipeline's asset id; the console can re-run it when a preset carries that id.
  const rerunTarget = React.useCallback((assetId: string | null): string | null => {
    if (!assetId) return null;
    const preset = PRESET_ASSETS.find((a) => assetIdFor(a.gcs) === assetId);
    if (preset) return preset.id;
    if (target.startsWith("gs://") && assetIdFor(target) === assetId) return target;
    return null;
  }, [target]);

  const select = React.useCallback(
    (next: string, uploaded?: { name: string; objectUrl: string }) => {
      setTarget(next);
      setUpload(uploaded ?? (next.startsWith("gs://") ? upload : null));
      setStageNote(null);
      setActiveSecond(null);
    },
    [upload],
  );

  const run = React.useCallback(
    (asset: string) => {
      setTab("review");
      setSegment("checks");
      setTarget(asset);
      setStageNote(null);
      setActiveSecond(null);
      start(asset, muted, faults);
    },
    [start, muted, faults],
  );

  const toggleMute = React.useCallback((gate: GateName) => {
    setMuted((prev) => (prev.includes(gate) ? prev.filter((g) => g !== gate) : [...prev, gate]));
  }, []);

  // One fault kind for now: the gate raises a TimeoutError before it calls its
  // instrument, so nothing is spent and the ERROR lands in Loki and Influx.
  const toggleFault = React.useCallback((gate: GateName) => {
    setFaults((prev) => {
      if (prev[gate]) {
        const next = { ...prev };
        delete next[gate];
        return next;
      }
      return { ...prev, [gate]: "timeout" };
    });
  }, []);

  const seek = React.useCallback(
    (seconds: number) => {
      setActiveSecond(seconds);
      const video = videoRef.current;
      if (!video || !clipReady) {
        setStageNote(
          `This clip is not streaming here, so ${seconds}s cannot be played. The console serves preloaded clips from Cloud Storage and has no credentials in this environment.`,
        );
        return;
      }
      setStageNote(null);
      video.currentTime = seconds;
      void video.play().catch(() => {});
    },
    [clipReady],
  );

  const findings = React.useMemo(() => buildFindings(state.gates), [state.gates]);
  const markers = React.useMemo(
    () =>
      collectMarkers(
        findings.map((finding) => ({
          text: finding.text,
          source: finding.gate,
          tone: finding.status === "PASS" ? ("pass" as const) : ("block" as const),
        })),
      ),
    [findings],
  );
  const notes = React.useMemo(
    () => verdictNotes(state.verdict?.reasons ?? [], findings),
    [state.verdict, findings],
  );

  const preset = presetById(target);
  const stageAsset: StageAsset = preset
    ? { kind: "preset", preset }
    : {
        kind: "upload",
        name: upload?.name ?? labelForTarget(target),
        objectUrl: upload?.objectUrl ?? null,
      };

  // The badge counts issues; a PASS sentence is an attestation, not a finding to fix.
  const issueCount = findings.filter((finding) => finding.status !== "PASS").length;
  const attestationCount = findings.length - issueCount;

  const stateLine =
    state.phase === "running"
      ? (state.step ?? "The gates are reading this clip.")
      : state.phase === "lost"
        ? "The event stream was lost, so nothing was cleared."
        : state.verdict
          ? issueCount > 0
            ? `${issueCount} issue${issueCount === 1 ? "" : "s"} from the four gates${
                markers.length > 0 ? ". Click a marker or a time to watch one" : ""
              }.`
            : `No issue from the four gates, ${attestationCount} attestation${attestationCount === 1 ? "" : "s"}.`
          : "Press Run airlock to read this clip against the four gates.";

  // The caption line reports where the run is, not what it decided: the verdict
  // has its own colour in the column, and a count of findings is not an alarm.
  const stateTone =
    state.phase === "running"
      ? ("accent" as const)
      : state.phase === "lost"
        ? ("block" as const)
        : ("quiet" as const);

  return (
    <TooltipProvider delayDuration={200}>
      <Tabs value={tab} onValueChange={setTab} className="fit-screen flex flex-col">
        <header className="shrink-0 border-b border-line bg-surface">
          <div className="mx-auto flex min-h-12 w-full max-w-[1920px] flex-wrap items-center gap-x-4 gap-y-1 px-4 py-1.5 min-[1100px]:h-12 min-[1100px]:flex-nowrap min-[1100px]:py-0">
            <Wordmark />
            <span className="hidden h-5 w-px bg-line md:block" aria-hidden="true" />
            <TabsList aria-label="Console views">
              <TabsTrigger value="review">Review</TabsTrigger>
              <TabsTrigger value="trace">Trace</TabsTrigger>
              <TabsTrigger value="queue">
                Queue
                {(incidentsView.incidents ? incidentsView.incidents.length : queue.length) > 0 && (
                  <span className="tabular font-mono text-[11px] text-ink-soft">
                    {incidentsView.incidents ? incidentsView.incidents.length : queue.length}
                  </span>
                )}
              </TabsTrigger>
            </TabsList>
            <div className="ml-auto flex items-center gap-4">
              <EnvBadge environment={environment} mock={mock} />
              <Button
                variant="accent"
                size="lg"
                disabled={busy}
                onClick={() => run(target)}
                aria-busy={busy}
              >
                {busy ? "Running the airlock" : "Run airlock"}
              </Button>
            </div>
          </div>
        </header>

        <main
          id="main-content"
          className="fit-region mx-auto flex w-full max-w-[1920px] flex-1 flex-col px-4 py-2.5"
        >
          <TabsContent value="review" className="fit-region flex flex-1 flex-col">
            <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 min-[1100px]:grid-cols-[minmax(0,1fr)_420px] min-[1100px]:grid-rows-[minmax(0,1fr)]">
              <div className="flex min-h-0 min-w-0 flex-col gap-2">
                <Stage
                  asset={stageAsset}
                  phase={state.phase}
                  markers={markers}
                  note={stageNote}
                  stateLine={stateLine}
                  stateTone={stateTone}
                  videoRef={videoRef}
                  activeSecond={activeSecond}
                  hoverSecond={hoverSecond}
                  onSeek={seek}
                  onHover={setHoverSecond}
                  onReadyChange={setClipReady}
                />
                <p className="shrink-0 px-1 text-[12px] leading-[1.4] text-ink-soft">{SOURCES_LINE}</p>
                <AssetStrip target={target} onSelect={select} disabled={busy} />
              </div>

              <div className="flex min-h-0 min-w-0 flex-col gap-2">
                <VerdictSummary state={state} onRetry={() => retry(muted, faults)} />

                <Tabs
                  value={segment}
                  onValueChange={setSegment}
                  className="flex min-h-0 flex-1 flex-col rounded-[4px] border border-line bg-surface"
                >
                  <TabsList
                    aria-label="What to read about this run"
                    className="shrink-0 border-b border-line px-1"
                  >
                    <SegmentTrigger value="checks">Checks</SegmentTrigger>
                    <SegmentTrigger value="findings">
                      Findings
                      <span className="tabular font-mono text-[11px] text-ink-soft">
                        {issueCount}
                      </span>
                    </SegmentTrigger>
                    <SegmentTrigger value="record">Record</SegmentTrigger>
                  </TabsList>

                  <TabsContent value="checks" className="fit-scroll flex-1">
                    <ChecksList
                      state={state}
                      reading={instruments}
                      mute={muted}
                      onToggleMute={toggleMute}
                      faults={faults}
                      onToggleFault={toggleFault}
                      controlsDisabled={busy}
                    />
                  </TabsContent>

                  <TabsContent value="findings" className="fit-scroll flex-1">
                    <FindingsThread
                      findings={findings}
                      notes={notes}
                      phase={state.phase}
                      step={state.step}
                      activeSecond={activeSecond}
                      onSeek={seek}
                      onHover={setHoverSecond}
                    />
                  </TabsContent>

                  <TabsContent value="record" className="fit-scroll flex-1">
                    <DecisionRecord
                      state={state}
                      dashboardUrl={dashboardUrl}
                      review={review}
                      onReview={(role) => void submitReview(role)}
                    />
                  </TabsContent>
                </Tabs>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="trace" className="fit-region flex flex-1 flex-col">
            <Panel className="flex min-h-0 flex-1 flex-col">
              <PanelHeader>
                <PanelTitle>
                  Event trace
                  {state.target && (
                    <span className="ml-2 normal-case tracking-normal">
                      {labelForTarget(state.target)}
                    </span>
                  )}
                </PanelTitle>
                <span className="tabular font-mono text-[10.5px] text-ink-soft">
                  {state.rows.length} event{state.rows.length === 1 ? "" : "s"}
                </span>
              </PanelHeader>
              <div className="fit-scroll flex-1">
                <Timeline state={state} dashboardUrl={dashboardUrl} onRetry={() => retry(muted, faults)} />
              </div>
            </Panel>
          </TabsContent>

          <TabsContent value="queue" className="fit-region flex flex-1 flex-col">
            <div className="fit-scroll flex-1 space-y-3">
              {incidentsView.incidents ? (
                <Panel>
                  <PanelHeader>
                    <PanelTitle>Open incidents in Grafana</PanelTitle>
                    <span className="tabular font-mono text-[10.5px] text-ink-soft">
                      {incidentsView.incidents.length} incident{incidentsView.incidents.length === 1 ? "" : "s"}
                      {incidentsView.mock ? ", mock" : ""}
                      {incidentsView.error ? ", last good reading" : ""}
                    </span>
                  </PanelHeader>
                  {incidentsView.error && (
                    <p className="border-b border-line px-3 py-2 text-[12px] leading-[1.45] text-warn">
                      Grafana did not answer the last refresh ({incidentsView.error}); this is the last list it gave.
                    </p>
                  )}
                  <IncidentQueue
                    incidents={incidentsView.incidents}
                    onRerun={run}
                    rerunTarget={rerunTarget}
                    busy={busy}
                  />
                </Panel>
              ) : (
                <Panel>
                  <PanelHeader>
                    <PanelTitle>
                      {incidentsView.loading ? "Reading the open incidents in Grafana" : "Blocked in this browser (offline fallback)"}
                    </PanelTitle>
                    <span className="tabular font-mono text-[10.5px] text-ink-soft">
                      {queue.length} run{queue.length === 1 ? "" : "s"}
                    </span>
                  </PanelHeader>
                  {!incidentsView.loading && (
                    <p className="border-b border-line px-3 py-2 text-[12px] leading-[1.45] text-warn">
                      Grafana did not answer ({incidentsView.error ?? "no reading yet"}), so this list is the runs of this
                      browser that ended BLOCK, kept in local storage. It is not the incident queue.
                    </p>
                  )}
                  <BlockQueue entries={queue} onRerun={run} busy={busy} />
                </Panel>
              )}
              <Panel>
                <PanelHeader>
                  <PanelTitle>How this queue works</PanelTitle>
                </PanelHeader>
                <PanelBody>
                  <p className="max-w-[80ch] text-[13px] leading-[1.55] text-ink-soft">
                    The queue is Grafana&apos;s list of open Airlock incidents, read through the
                    Incident API. The escalation agent opens one per asset and motive when a BLOCK
                    needs a human, and later runs of the same asset join it instead of opening
                    another; the investigator&apos;s note and the Loki lines it cites are in the
                    incident. Marking a run reviewed in the Record resolves its incident and writes
                    an annotation tagged reviewed. Re-run sends the asset through the airlock again,
                    which is how a reviewer confirms that a block caused by a degraded control clears
                    once the control is healthy. When Grafana does not answer, the runs of this
                    browser that ended BLOCK are shown instead, and said to be that.
                  </p>
                </PanelBody>
              </Panel>
            </div>
          </TabsContent>
        </main>

        <footer className="shrink-0 border-t border-line bg-surface px-4 py-1.5">
          <div className="mx-auto w-full max-w-[1920px]">
            <StatTiles
              stats={instruments.stats}
              loading={instruments.loading}
              outage={instruments.outage}
            />
            <SpecStrip lastRunMs={state.elapsedMs} />
          </div>
        </footer>
      </Tabs>
    </TooltipProvider>
  );
}
