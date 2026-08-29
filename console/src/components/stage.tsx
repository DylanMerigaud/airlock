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
 * The scrubber a review tool would give you: the clip laid flat, with a marker
 * on every second a gate wrote a finding at, coloured by the gate that wrote
 * it. Click a marker and the player jumps there; the matching finding in the
 * thread lights up at the same time.
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
    <div className="border-t border-line-soft bg-card-sunk px-4 pb-2.5 pt-2.5">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <h2 className="label-micro text-ink-soft">
          Findings on the clip
          <span className="ml-2 normal-case tracking-normal">
            {markers.length === 0
              ? "none anchored yet"
              : `${markers.length} anchored to a second`}
          </span>
        </h2>
        <ul className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {GATE_ORDER.map((gate) => (
            <li key={gate} className="flex items-center gap-1.5">
              <span className={cn("h-[7px] w-[3px]", GATE_DOT[gate])} aria-hidden="true" />
              <span className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-ink-soft">
                {gate}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="relative mt-3 h-[34px]">
        <span
          aria-hidden="true"
          className="absolute inset-x-0 top-[6px] h-[6px] rounded-[3px] bg-[#ded8c9]"
        />
        <span
          aria-hidden="true"
          className="absolute left-0 top-[6px] h-[6px] rounded-[3px] bg-ink/70"
          style={{ width: `${played}%` }}
        />
        {position !== null && (
          <span
            aria-hidden="true"
            className="absolute top-[3px] h-[12px] w-[2px] -translate-x-1/2 rounded-[1px] bg-ink"
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
              className="group absolute top-0 flex h-[34px] w-[24px] -translate-x-1/2 flex-col items-center"
              style={{ left: `${left}%` }}
            >
              <span className="sr-only">
                Play from {marker.label}, flagged by {marker.sources.join(" and ")}
              </span>
              <span
                aria-hidden="true"
                className={cn(
                  "flex h-[18px] w-[5px] flex-col overflow-hidden rounded-[2px] border transition-all",
                  lit
                    ? "scale-y-110 border-ink shadow-[0_0_0_2px_rgba(178,60,11,0.28)]"
                    : "border-card group-hover:border-ink",
                )}
              >
                {marker.sources.map((source) => (
                  <span key={source} className={cn("flex-1", hueFor(source))} />
                ))}
              </span>
              <span
                aria-hidden="true"
                className={cn(
                  "tabular mt-[2px] font-mono text-[9px] leading-none transition-colors",
                  lit ? "text-ink" : "text-ink-soft",
                )}
              >
                {marker.label}
              </span>
            </button>
          );
        })}
      </div>

      <div className="flex items-center justify-between font-mono text-[9.5px] text-ink-soft">
        <span className="tabular">{position === null ? "0:00" : clock(position)}</span>
        {markers.length === 0 && (
          <span className="hidden px-3 text-center sm:inline">
            A finding that names a second in the clip lands on this bar, and plays it.
          </span>
        )}
        <span className="tabular">{clock(duration)}</span>
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
  stateTone: "quiet" | "ember" | "block" | "pass";
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
    <figure id="stage" className="overflow-hidden rounded-[5px] border border-line bg-card">
      <div className="relative aspect-video w-full bg-[#171510]">
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
            className="h-full w-full object-contain"
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
          <div className="flex h-full w-full items-center justify-center px-8 text-center">
            <p className="max-w-[46ch] font-mono text-[12px] leading-[1.6] text-[#e8e3d7]">
              This upload lives in Cloud Storage and has no local copy to play here. Run it, or
              pick a preloaded clip to watch one.
            </p>
          </div>
        )}

        {preset?.origin === "synthetic" && (
          <p className="pointer-events-none absolute left-3 top-3 rounded-[2px] bg-[#171510]/85 px-2 py-1 font-mono text-[10px] leading-none tracking-[0.06em] text-[#f3e4d4]">
            synthetic test asset, Veo 3.1 on Vertex AI, C2PA signed
          </p>
        )}

        {phase === "running" && (
          <p className="pointer-events-none absolute right-3 top-3 flex items-center gap-1.5 rounded-[2px] bg-[#171510]/85 px-2 py-1 font-mono text-[10px] uppercase leading-none tracking-[0.14em] text-[#f4b98a]">
            <span className="h-[5px] w-[5px] rounded-full bg-ember lamp-live" aria-hidden="true" />
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

      <figcaption className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2 border-t border-line-soft px-4 py-3">
        <div className="min-w-0">
          <p className="display text-[16px] leading-tight text-ink">{title}</p>
          <p className="mt-1 font-mono text-[10.5px] leading-[1.5] text-ink-soft">
            {preset
              ? `${preset.duration}, ${preset.origin}, ${preset.provenance}`
              : "uploaded clip, MP4"}
          </p>
        </div>
        <p
          className={cn(
            "max-w-[48ch] text-[12.5px] leading-[1.5]",
            stateTone === "ember"
              ? "text-ember"
              : stateTone === "block"
                ? "text-block"
                : stateTone === "pass"
                  ? "text-pass"
                  : "text-ink-mid",
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
            "border-t px-4 py-2.5 text-[11.5px] leading-[1.5]",
            note
              ? "border-warn-line bg-warn-wash text-warn"
              : "border-line-soft bg-card-sunk text-ink-soft",
          )}
        >
          {note ??
            "This clip is not streaming: the console serves preloaded clips from Cloud Storage and has no credentials here. The poster, the scrubber and every finding still work."}
        </p>
      )}
    </figure>
  );
}
