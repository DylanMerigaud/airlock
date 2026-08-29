"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { splitTimecodes } from "@/lib/timecodes";

/**
 * A finding, with its timecodes turned into buttons that seek the clip. This is
 * the gesture the whole review rests on: read what a gate says, then watch the
 * second it read it at.
 */
export function FindingText({
  text,
  onSeek,
  className,
}: {
  text: string;
  onSeek: (seconds: number) => void;
  className?: string;
}) {
  const parts = React.useMemo(() => splitTimecodes(text), [text]);

  return (
    <span className={className}>
      {parts.map((part, index) =>
        part.kind === "text" ? (
          <React.Fragment key={index}>{part.text}</React.Fragment>
        ) : (
          <button
            key={index}
            type="button"
            onClick={() => onSeek(part.seconds)}
            title={`Play the clip from ${part.label}`}
            className={cn(
              "mx-[1px] inline-flex translate-y-[1px] items-center gap-1 rounded-[2px] border border-ember-line bg-ember-wash",
              "px-1.5 py-[1px] font-mono text-[11px] leading-[1.35] tracking-[0.02em] text-ember",
              "transition-colors hover:border-ember hover:bg-ember hover:text-card",
            )}
          >
            <svg viewBox="0 0 10 10" width="7" height="7" aria-hidden="true">
              <path d="M2.5 1.5 8 5l-5.5 3.5z" fill="currentColor" />
            </svg>
            <span className="sr-only">Play the clip from </span>
            {part.label}
          </button>
        ),
      )}
    </span>
  );
}
