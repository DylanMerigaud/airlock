import { ms } from "@/lib/utils";

const SPECS = [
  "gemini-2.5-pro and gemini-2.5-flash on Vertex AI",
  "google-adk on Vertex AI Agent Engine",
  "mcp-grafana 1.3.0 on Cloud Run",
  "Video Intelligence API",
  "c2pa-python 0.37",
  "Apache-2.0",
];

/** What the console runs on, one line, the way a colophon sits under a page. */
export function SpecStrip({ lastRunMs }: { lastRunMs: number | null }) {
  return (
    <section
      aria-label="What this console runs on"
      className="border-t border-line-soft py-3 font-mono text-[10px] leading-[1.7] tracking-[0.02em] text-ink-soft"
    >
      {SPECS.join("  ·  ")}
      {"  ·  last run "}
      {lastRunMs === null ? "not measured yet" : ms(lastRunMs)}
    </section>
  );
}
