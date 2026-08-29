"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { clock, durationHint, type Marker } from "@/lib/timecodes";
import { GATE_ORDER, type GateName } from "@/lib/events";
import { GATE_DOT } from "@/lib/instrument";
import type { PresetAsset } from "@/lib/assets";
import type { RunPhase } from "@/lib/use-run";

export type StageAsset =
  | { kind: "preset"; preset: PresetAsset }
  | { kind: "upload"; name: string; objectUrl: string | null };

function hueFor(source: string): string {
  return GATE_DOT[source as GateName] ?? "bg-ink";
}

/**
 * The clip laid flat, with a marker on every second a gate wrote a finding at,
 * coloured by the gate that wrote it. Click a marker and the player jumps
 * there; the matching finding in the thread lights up at the same time.
 */
function Scrubber({
  markers,
  duration,
  position,
  activeSecond,
  hoverSecond,
  onSeek,
  onHover,
}: {
  markers: Marker[];
  duration: number;
  position: number | null;
  activeSecond: number | null;
  hoverSecond: number | null;
  onSeek: (seconds: number) => void;
  onHover: (seconds: number | null) => void;
}) {
  const played = position === null ? 0 : Math.min(100, Math.max(0, (position / duration) * 100));

  return (
    <div className="px-4 pt-2.5">
      <h2 className="sr-only">Findings on the clip</h2>
      <div className="relative h-[30px]">
        <span
          aria-hidden="true"
          className="absolute inset-x-0 top-[5px] h-[4px] rounded-[2px] bg-line"
        />
        <span
          aria-hidden="true"
          className="absolute left-0 top-[5px] h-[4px] rounded-[2px] bg-line-strong"
          style={{ width: `${played}%` }}
        />
        {position !== null && (
          <span
            aria-hidden="true"
            className="absolute top-[2px] h-[10px] w-[2px] -translate-x-1/2 bg-ink"
            style={{ left: `${played}%` }}
          />
        )}

        {markers.map((marker) => {
          const left = Math.min(100, Math.max(0, (marker.seconds / duration) * 100));
          const lit = activeSecond === marker.seconds || hoverSecond === marker.seconds;
          return (
            <button
              key={marker.seconds}
              type="button"
              onClick={() => onSeek(marker.seconds)}
              onMouseEnter={() => onHover(marker.seconds)}
              onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(marker.seconds)}
              onBlur={() => onHover(null)}
              className="group absolute top-0 flex h-[30px] w-[26px] -translate-x-1/2 flex-col items-center"
              style={{ left: `${left}%` }}
            >
              <span className="sr-only">
                Play from {marker.label}, flagged by {marker.sources.join(" and ")}
              </span>
              <span
                aria-hidden="true"
                className={cn(
                  "flex h-[14px] w-[4px] flex-col overflow-hidden rounded-[1px] border",
                  lit ? "border-ink" : "border-surface group-hover:border-line-strong",
                )}
              >
                {marker.sources.map((source) => (
                  <span key={source} className={cn("flex-1", hueFor(source))} />
                ))}
              </span>
              <span
                aria-hidden="true"
                className={cn(
                  "tabular mt-[2px] font-mono text-[9px] leading-none",
                  lit ? "text-ink" : "text-ink-soft",
                )}
              >
                {marker.label}
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-1 flex items-center justify-between gap-4">
        <span className="tabular font-mono text-[10px] text-ink-soft">
          {position === null ? "0:00" : clock(position)}
        </span>
        <ul className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
          {GATE_ORDER.map((gate) => (
            <li key={gate} className="flex items-center gap-1.5">
              <span className={cn("h-[8px] w-[3px]", GATE_DOT[gate])} aria-hidden="true" />
              <span className="font-mono text-[9.5px] uppercase tracking-[0.07em] text-ink-soft">
                {gate}
              </span>
            </li>
          ))}
          <li className="font-mono text-[9.5px] text-ink-soft">
            {markers.length === 0
              ? "no finding anchored to a second yet"
              : `${markers.length} anchored, click one to play it`}
          </li>
        </ul>
        <span className="tabular font-mono text-[10px] text-ink-soft">{clock(duration)}</span>
      </div>
    </div>
  );
}

export function Stage({
  asset,
  phase,
  markers,
  note,
  stateLine,
  stateTone,
  videoRef,
  activeSecond,
  hoverSecond,
  onSeek,
  onHover,
  onReadyChange,
}: {
  asset: StageAsset;
  phase: RunPhase;
  markers: Marker[];
  note: string | null;
  stateLine: string;
  stateTone: "quiet" | "accent" | "block";
  videoRef: React.RefObject<HTMLVideoElement | null>;
  activeSecond: number | null;
  hoverSecond: number | null;
  onSeek: (seconds: number) => void;
  onHover: (seconds: number | null) => void;
  onReadyChange: (ready: boolean) => void;
}) {
  const [failed, setFailed] = React.useState(false);
  const [position, setPosition] = React.useState<number | null>(null);
  const [measured, setMeasured] = React.useState<number | null>(null);

  const preset = asset.kind === "preset" ? asset.preset : null;
  const source = asset.kind === "preset" ? `/api/asset/${asset.preset.id}` : asset.objectUrl;
  const title = asset.kind === "preset" ? asset.preset.name : asset.name;

  const hinted = preset ? durationHint(preset.duration) : null;
  const longest = markers.length > 0 ? markers[markers.length - 1].seconds : 0;
  const duration = measured ?? hinted ?? Math.max(30, Math.ceil(longest * 1.15));

  // A new clip is a new measurement: nothing failed, nothing played yet.
  React.useEffect(() => {
    setFailed(false);
    setMeasured(null);
    setPosition(null);
    onReadyChange(false);
  }, [source, onReadyChange]);

  // The clip is what the gates are reading, so it runs while they read it.
  React.useEffect(() => {
    const video = videoRef.current;
    if (!video || !source) return;
    if (phase === "running") {
      video.muted = true;
      video.loop = true;
      void video.play().catch(() => {
        // Autoplay refused: the poster stays and the controls still work.
      });
    } else {
      video.loop = false;
      if (!video.paused) video.pause();
    }
  }, [phase, source, videoRef]);

  return (
    <figure id="stage" className="flex min-h-0 flex-1 flex-col">
      <div className="stage-box overflow-hidden rounded-[4px] border border-line bg-[#0f0f0f]">
        {source ? (
          <video
            ref={videoRef}
            key={source}
            src={source}
            poster={preset?.poster}
            controls
            playsInline
            preload="metadata"
            aria-label={`Clip under review: ${title}`}
            className="absolute inset-0 h-full w-full object-contain"
            onLoadedMetadata={(event) => {
              const value = event.currentTarget.duration;
              if (Number.isFinite(value) && value > 0) setMeasured(value);
              setFailed(false);
              onReadyChange(true);
            }}
            onTimeUpdate={(event) => setPosition(event.currentTarget.currentTime)}
            onError={() => {
              setFailed(true);
              onReadyChange(false);
            }}
          >
            {preset && (
              <track
                kind="captions"
                srcLang="en"
                label="English"
                src={`/captions/${preset.id}.vtt`}
              />
            )}
          </video>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center px-8 text-center">
            <p className="max-w-[46ch] font-mono text-[12px] leading-[1.6] text-[#e5e5e5]">
              This upload lives in Cloud Storage and has no local copy to play here. Run it, or
              pick a preloaded clip to watch one.
            </p>
          </div>
        )}

        {preset?.origin === "synthetic" && (
          <p className="pointer-events-none absolute left-2.5 top-2.5 rounded-[2px] bg-[#0f0f0f]/85 px-2 py-1 font-mono text-[10px] leading-none text-[#f1f1f1]">
            synthetic test asset, Veo 3.1 on Vertex AI, C2PA signed
          </p>
        )}

        {phase === "running" && (
          <p className="pointer-events-none absolute right-2.5 top-2.5 flex items-center gap-1.5 rounded-[2px] bg-[#0f0f0f]/85 px-2 py-1 font-mono text-[10px] uppercase leading-none tracking-[0.08em] text-[#f1f1f1]">
            <span className="h-[6px] w-[6px] rounded-[1px] bg-[#8ab4f8]" aria-hidden="true" />
            gates reading
          </p>
        )}
      </div>

      <Scrubber
        markers={markers}
        duration={duration}
        position={position}
        activeSecond={activeSecond}
        hoverSecond={hoverSecond}
        onSeek={onSeek}
        onHover={onHover}
      />

      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-5 gap-y-1 border-t border-line px-1 pt-2">
        <div className="min-w-0">
          <span className="text-[13px] font-medium leading-tight text-ink">{title}</span>
          <span className="ml-2 font-mono text-[10.5px] text-ink-soft">
            {preset
              ? `${preset.duration}, ${preset.origin}, ${preset.provenance}`
              : "uploaded clip, MP4"}
          </span>
        </div>
        <p
          className={cn(
            "max-w-[62ch] text-[12.5px] leading-[1.45]",
            stateTone === "accent"
              ? "text-accent"
              : stateTone === "block"
                ? "text-block"
                : "text-ink-soft",
          )}
          aria-live="polite"
        >
          {stateLine}
        </p>
      </figcaption>

      {(failed || note) && (
        <p
          role="status"
          className={cn(
            "fade-in mt-1.5 rounded-[2px] border px-2.5 py-1.5 text-[12px] leading-[1.45]",
            note ? "border-line bg-surface text-warn" : "border-line bg-surface text-ink-soft",
          )}
        >
          {note ??
            "This clip is not streaming: the console serves preloaded clips from Cloud Storage and has no credentials here. The poster, the scrubber and every finding still work."}
        </p>
      )}
    </figure>
  );
}
