import { duration } from "@/lib/utils";

const SPECS = [
  "gemini-2.5-pro and gemini-2.5-flash on Vertex AI",
  "google-adk on Vertex AI Agent Engine",
  "mcp-grafana 1.3.0 on Cloud Run",
  "Video Intelligence API",
  "c2pa-python 0.37",
  "Apache-2.0",
];

/**
 * What the console runs on, the way a colophon sits under a page. One line
 * when it fits, two rows when the window is narrow: it never truncates.
 */
export function SpecStrip({ lastRunMs }: { lastRunMs: number | null }) {
  return (
    <p
      aria-label="What this console runs on"
      className="font-mono text-[10px] leading-[1.5] text-ink-soft"
    >
      {SPECS.join("  ·  ")}
      {"  ·  last run "}
      {lastRunMs === null ? "not measured yet" : duration(lastRunMs)}
    </p>
  );
}
