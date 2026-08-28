import { cn } from "@/lib/utils";
import type { ChipStatus } from "@/lib/events";

const TONE: Record<ChipStatus, { dot: string; text: string; ring: string }> = {
  PENDING: { dot: "bg-ink-faint/50", text: "text-ink-faint", ring: "border-line" },
  RUNNING: { dot: "bg-amber lamp-live", text: "text-amber", ring: "border-amber/35" },
  PASS: { dot: "bg-pass", text: "text-pass", ring: "border-pass/35" },
  BLOCK: { dot: "bg-block-deep", text: "text-block", ring: "border-block-deep/45" },
  ERROR: { dot: "bg-block-deep", text: "text-block", ring: "border-block-deep/45" },
};

export function StatusChip({ status, className }: { status: ChipStatus; className?: string }) {
  const tone = TONE[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[2px] border bg-panel-2 px-1.5 py-1",
        "font-mono text-[10px] uppercase leading-none tracking-[0.14em]",
        tone.ring,
        tone.text,
        className,
      )}
    >
      <span className={cn("h-[5px] w-[5px] rounded-full", tone.dot)} aria-hidden="true" />
      {status}
    </span>
  );
}
