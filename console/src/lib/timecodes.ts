/**
 * Findings are written by the gates in plain sentences, and the useful ones
 * carry the second of the clip they were read at: "logo at 16.12s", "first at
 * 7.5s", "(first at 0.0s)". The console turns those into buttons that seek the
 * player, which is the reviewer's core gesture: read the finding, watch it.
 *
 * The anchor is deliberately narrow. A bare "533 s ago" in a health line is not
 * a position in the clip, and "9 out of 10 sommeliers" is not one either, so a
 * number only becomes a timecode when it is introduced by "at" or when the unit
 * is glued to it ("16.12s").
 */

export type FindingPart =
  | { kind: "text"; text: string }
  | { kind: "time"; label: string; seconds: number };

const PATTERN = /(\bat\s+)?(\d+(?:\.\d+)?)(\s*)s(?![a-z0-9])/gi;

export function splitTimecodes(text: string): FindingPart[] {
  const parts: FindingPart[] = [];
  let last = 0;
  PATTERN.lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = PATTERN.exec(text)) !== null) {
    const [whole, at, digits, gap] = match;
    // "at 7.5s" and "16.12s" are positions; "533 s ago" is a duration.
    if (!at && gap !== "") continue;
    const start = match.index + (at ? at.length : 0);
    if (start > last) parts.push({ kind: "text", text: text.slice(last, start) });
    parts.push({ kind: "time", label: `${digits}s`, seconds: Number(digits) });
    last = match.index + whole.length;
  }

  if (parts.length === 0) return [{ kind: "text", text }];
  if (last < text.length) parts.push({ kind: "text", text: text.slice(last) });
  return parts;
}


export type MarkerTone = "block" | "pass" | "warn";

export type Marker = {
  seconds: number;
  label: string;
  sources: string[];
  tone: MarkerTone;
};

const TONE_RANK: Record<MarkerTone, number> = { pass: 0, warn: 1, block: 2 };

/**
 * Every timecode a run produced, merged by second so two gates reading the same
 * frame make one tick, in clip order.
 */
export function collectMarkers(
  findings: Array<{ text: string; source: string; tone: MarkerTone }>,
): Marker[] {
  const merged = new Map<number, Marker>();
  for (const finding of findings) {
    for (const part of splitTimecodes(finding.text)) {
      if (part.kind !== "time") continue;
      const at = merged.get(part.seconds);
      if (!at) {
        merged.set(part.seconds, {
          seconds: part.seconds,
          label: part.label,
          sources: [finding.source],
          tone: finding.tone,
        });
        continue;
      }
      if (!at.sources.includes(finding.source)) at.sources.push(finding.source);
      if (TONE_RANK[finding.tone] > TONE_RANK[at.tone]) at.tone = finding.tone;
    }
  }
  return [...merged.values()].sort((a, b) => a.seconds - b.seconds);
}

/** "30 s excerpt" and "8 s" both mean a clip that long. */
export function durationHint(label: string): number | null {
  const match = /(\d+(?:\.\d+)?)\s*s\b/.exec(label);
  return match ? Number(match[1]) : null;
}

/** How a position in the clip is written everywhere: 7.5s, 16.12s, 1:04. */
export function stamp(seconds: number): string {
  if (seconds < 60) return `${Number(seconds.toFixed(2))}s`;
  return clock(seconds);
}

export function clock(seconds: number): string {
  const whole = Math.floor(seconds);
  const mins = Math.floor(whole / 60);
  const secs = whole % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}
