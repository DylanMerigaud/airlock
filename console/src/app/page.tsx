import { ConsoleShell } from "@/components/console-shell";

// The console reads its environment at request time, not at build time.
export const dynamic = "force-dynamic";

const DEFAULT_DASHBOARD =
  "https://narrowsubmarine1895.grafana.net/public-dashboards/97860661238c4536a743e0d858aef845";

function environmentLabel(): string {
  const resource = process.env.AGENT_ENGINE_RESOURCE ?? "";
  const match = /locations\/([^/]+)/.exec(resource);
  return `Vertex AI Agent Engine, ${match ? match[1] : "us-central1"}`;
}

export default function Page() {
  return (
    <ConsoleShell
      dashboardUrl={process.env.AIRLOCK_PUBLIC_DASHBOARD_URL || DEFAULT_DASHBOARD}
      environment={environmentLabel()}
      mock={process.env.AIRLOCK_MOCK === "1"}
    />
  );
}
