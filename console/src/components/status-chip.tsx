import { cn } from "@/lib/utils";
import type { ChipStatus } from "@/lib/events";

/** A mark and a word. The mark carries the colour, the word carries the text. */
const TONE: Record<ChipStatus, { mark: string; text: string }> = {
  PENDING: { mark: "bg-line-strong", text: "text-ink-soft" },
  RUNNING: { mark: "bg-accent", text: "text-accent" },
  PASS: { mark: "bg-pass", text: "text-ink" },
  BLOCK: { mark: "bg-block", text: "text-block" },
  ERROR: { mark: "bg-block", text: "text-block" },
};

export function StatusChip({ status, className }: { status: ChipStatus; className?: string }) {
  const tone = TONE[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[2px] border border-line px-1.5 py-1",
        "font-mono text-[10px] uppercase leading-none tracking-[0.08em]",
        tone.text,
        className,
      )}
    >
      <span className={cn("h-[6px] w-[6px] rounded-[1px]", tone.mark)} aria-hidden="true" />
      {status}
    </span>
  );
}
