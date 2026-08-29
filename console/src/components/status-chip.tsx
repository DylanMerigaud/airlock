import { cn } from "@/lib/utils";
import type { ChipStatus } from "@/lib/events";

const TONE: Record<ChipStatus, { dot: string; text: string; ring: string; fill: string }> = {
  PENDING: { dot: "bg-ink-soft/45", text: "text-ink-soft", ring: "border-line", fill: "bg-card-sunk" },
  RUNNING: { dot: "bg-ember lamp-live", text: "text-ember", ring: "border-ember-line", fill: "bg-ember-wash" },
  PASS: { dot: "bg-pass", text: "text-pass", ring: "border-pass-line", fill: "bg-pass-wash" },
  BLOCK: { dot: "bg-block", text: "text-block", ring: "border-block-line", fill: "bg-block-wash" },
  ERROR: { dot: "bg-block", text: "text-block", ring: "border-block-line", fill: "bg-block-wash" },
};

export function StatusChip({ status, className }: { status: ChipStatus; className?: string }) {
  const tone = TONE[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[2px] border px-1.5 py-1",
        "font-mono text-[10px] uppercase leading-none tracking-[0.14em]",
        tone.ring,
        tone.text,
        tone.fill,
        className,
      )}
    >
      <span className={cn("h-[5px] w-[5px] rounded-full", tone.dot)} aria-hidden="true" />
      {status}
    </span>
  );
}
