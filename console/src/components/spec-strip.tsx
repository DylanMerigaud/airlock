import { ms } from "@/lib/utils";

const SPECS = [
  "gemini-2.5-pro and gemini-2.5-flash on Vertex AI",
  "google-adk on Vertex AI Agent Engine",
  "mcp-grafana 1.3.0 on Cloud Run",
  "Video Intelligence API",
  "c2pa-python 0.37",
  "Apache-2.0",
];

export function SpecStrip({ lastRunMs }: { lastRunMs: number | null }) {
  return (
    <section
      aria-label="What this console runs on"
      className="flex flex-wrap items-center gap-x-2 gap-y-2 rounded-[4px] border border-line-soft bg-hull px-3.5 py-3"
    >
      {SPECS.map((spec) => (
        <span
          key={spec}
          className="rounded-[2px] border border-line bg-panel px-2 py-1 font-mono text-[10px] leading-none tracking-[0.03em] text-ink-faint"
        >
          {spec}
        </span>
      ))}
      <span className="ml-auto font-mono text-[10px] tracking-[0.03em] text-ink-faint">
        last run {lastRunMs === null ? "not measured yet" : ms(lastRunMs)}
      </span>
    </section>
  );
}
