"""The deployment's coordinates, read from the environment in one place, with the values this
deployment uses as defaults.

Every Python caller (airlock, airlock_mcp, agents, scripts) reads a coordinate through a function
here, at call time, so a test's monkeypatch and a judge's export both take effect. The shell scripts
under infra/ and scripts/ cannot import this module; they name the same variables with the same
defaults (`PROJECT="${AIRLOCK_PROJECT:-airlock-agentic-cinema}"`), so one `export` changes both sides.

    uv run python -m airlock.settings      # print every variable, its effective value and where it came from

Two kinds of variable:
  - coordinates with a default (project, region, bucket, engine, Grafana stack URL, datasource uids,
    dashboard uid, the deployed service URLs, the keychain account): unset means this deployment;
  - telemetry endpoints and tokens (GRAFANA_INFLUX_*, GRAFANA_LOKI_*, the MCP bearers) with NO
    default: unset means "not configured", and the callers say so (gate telemetry is skipped with a
    warning, an MCP toolset refuses to build). A token is never given a default and never printed.

To run Airlock on another Google Cloud project and Grafana stack, export these before any command:
AIRLOCK_PROJECT, AIRLOCK_REGION, AIRLOCK_ASSETS_BUCKET, AGENT_ENGINE_RESOURCE (after `adk deploy`),
GRAFANA_URL, GRAFANA_INFLUX_URL, GRAFANA_INFLUX_USER, GRAFANA_LOKI_URL, GRAFANA_LOKI_USER,
AIRLOCK_MCP_URL (the mcp-grafana service), and the tokens through scripts/with_env.sh or Secret Manager.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any

DEFAULT_PROJECT = "airlock-agentic-cinema"
DEFAULT_PROJECT_NUMBER = "771466810465"
DEFAULT_REGION = "us-central1"
DEFAULT_BUCKET = "airlock-agentic-cinema-assets"
DEFAULT_ENGINE_RESOURCE = f"projects/{DEFAULT_PROJECT_NUMBER}/locations/{DEFAULT_REGION}/reasoningEngines/1737023312967499776"
DEFAULT_GRAFANA_URL = "https://narrowsubmarine1895.grafana.net"
DEFAULT_PROM_UID = "grafanacloud-prom"
DEFAULT_LOKI_UID = "grafanacloud-logs"
DEFAULT_DASHBOARD_UID = "airlock-gates"
DEFAULT_PUBLIC_DASHBOARD_URL = f"{DEFAULT_GRAFANA_URL}/public-dashboards/97860661238c4536a743e0d858aef845"
DEFAULT_GRAFANA_MCP_URL = f"https://airlock-mcp-grafana-{DEFAULT_PROJECT_NUMBER}.{DEFAULT_REGION}.run.app/mcp"
DEFAULT_AIRLOCK_MCP_SERVER_URL = f"https://airlock-mcp-{DEFAULT_PROJECT_NUMBER}.{DEFAULT_REGION}.run.app/mcp"
DEFAULT_CONSOLE_URL = f"https://airlock-console-{DEFAULT_PROJECT_NUMBER}.{DEFAULT_REGION}.run.app"
DEFAULT_KEYCHAIN_ACCOUNT = "dylanmerigaud"
DEFAULT_RUNTIME = "local"
DEFAULT_INCIDENT_DRILL = True


def _first(*names: str, default: str = "") -> str:
    """The first of these variables that is set and non-empty, else the default."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


# Google Cloud


def project() -> str:
    """GOOGLE_CLOUD_PROJECT (what the Google SDKs read) or AIRLOCK_PROJECT (what the infra scripts read)."""
    return _first("GOOGLE_CLOUD_PROJECT", "AIRLOCK_PROJECT", default=DEFAULT_PROJECT)


def region() -> str:
    return _first("GOOGLE_CLOUD_LOCATION", "AIRLOCK_REGION", default=DEFAULT_REGION)


def bucket() -> str:
    """The assets bucket (demo clips, calibration inputs, uploads), without the gs:// prefix."""
    return _first("AIRLOCK_ASSETS_BUCKET", default=DEFAULT_BUCKET)


def engine_resource() -> str:
    """The deployed reasoning engine: projects/<number>/locations/<region>/reasoningEngines/<id>."""
    return _first("AGENT_ENGINE_RESOURCE", default=DEFAULT_ENGINE_RESOURCE)


def runtime() -> str:
    """The label every Loki event carries: local, agent-engine, airlock-mcp, daily-proof."""
    return _first("AIRLOCK_RUNTIME", default=DEFAULT_RUNTIME)


# Grafana


def grafana_url() -> str:
    return _first("GRAFANA_URL", default=DEFAULT_GRAFANA_URL).rstrip("/")


def grafana_service_account_token() -> str:
    """The Editor token the bootstrap and the console use against the Grafana HTTP API. Never defaulted."""
    return os.environ.get("GRAFANA_SERVICE_ACCOUNT_TOKEN", "")


def prometheus_uid() -> str:
    """GRAFANA_PROM_UID, or the Grafana Cloud default; an EMPTY value means "ask list_datasources"."""
    return os.environ.get("GRAFANA_PROM_UID", DEFAULT_PROM_UID)


def loki_uid() -> str:
    """GRAFANA_LOKI_UID, or the Grafana Cloud default; an EMPTY value means "ask list_datasources"."""
    return os.environ.get("GRAFANA_LOKI_UID", DEFAULT_LOKI_UID)


def dashboard_uid() -> str:
    return _first("AIRLOCK_DASHBOARD_UID", default=DEFAULT_DASHBOARD_UID)


def public_dashboard_url() -> str:
    return _first("AIRLOCK_PUBLIC_DASHBOARD_URL", default=DEFAULT_PUBLIC_DASHBOARD_URL)


@dataclass(frozen=True)
class PushEndpoint:
    """One Grafana Cloud push endpoint (Influx line protocol for metrics, the Loki push API for
    events): a URL, the instance id as user, an access policy token. No default for any of the
    three: unset means the telemetry is not configured, and the caller says so."""

    name: str
    url: str
    user: str
    token: str

    @property
    def configured(self) -> bool:
        return bool(self.url)

    def missing(self) -> list[str]:
        """The variable names still unset, for an error message that names them."""
        return [f"{self.name}_{k}" for k, v in (("URL", self.url), ("USER", self.user), ("TOKEN", self.token)) if not v]


def influx() -> PushEndpoint:
    return PushEndpoint("GRAFANA_INFLUX", os.environ.get("GRAFANA_INFLUX_URL", ""), os.environ.get("GRAFANA_INFLUX_USER", ""),
                        os.environ.get("GRAFANA_INFLUX_TOKEN", ""))


def loki() -> PushEndpoint:
    return PushEndpoint("GRAFANA_LOKI", os.environ.get("GRAFANA_LOKI_URL", ""), os.environ.get("GRAFANA_LOKI_USER", ""),
                        os.environ.get("GRAFANA_LOKI_TOKEN", ""))


# MCP servers


def grafana_mcp_url() -> str:
    """The mcp-grafana service the agents call (AIRLOCK_MCP_URL). Defaults to the deployed one; the
    toolset still needs AIRLOCK_MCP_TOKEN, which has no default."""
    return _first("AIRLOCK_MCP_URL", default=DEFAULT_GRAFANA_MCP_URL)


def grafana_mcp_token() -> str:
    """The bearer mcp-grafana enforces (AIRLOCK_MCP_TOKEN). Never defaulted."""
    return os.environ.get("AIRLOCK_MCP_TOKEN", "")


def airlock_mcp_server_url() -> str:
    """The airlock-mcp service (the gates as tools), for its client script and the demo prep."""
    return _first("AIRLOCK_MCP_SERVER_URL", default=DEFAULT_AIRLOCK_MCP_SERVER_URL)


def airlock_mcp_server_token() -> str:
    """The bearer airlock-mcp enforces on its own transport (AIRLOCK_MCP_SERVER_TOKEN). Never defaulted."""
    return os.environ.get("AIRLOCK_MCP_SERVER_TOKEN", "")


def console_url() -> str:
    return _first("AIRLOCK_CONSOLE_URL", default=DEFAULT_CONSOLE_URL)


# Local machine and behaviour switches


def keychain_account() -> str:
    """The macOS keychain account the secrets are filed under (AIRLOCK_KEYCHAIN_ACCOUNT)."""
    return _first("AIRLOCK_KEYCHAIN_ACCOUNT", default=DEFAULT_KEYCHAIN_ACCOUNT)


def muted_gates() -> set[str]:
    """AIRLOCK_MUTE_GATE_TELEMETRY=rights,claim: gates whose pushes are silenced (the R1 demo from the env)."""
    return {x.strip() for x in os.environ.get("AIRLOCK_MUTE_GATE_TELEMETRY", "").split(",") if x.strip()}


def incident_drill() -> bool:
    """AIRLOCK_INCIDENT_DRILL: incidents are opened as drills unless set to "false"."""
    raw = os.environ.get("AIRLOCK_INCIDENT_DRILL")
    if raw is None:
        return DEFAULT_INCIDENT_DRILL
    return raw.strip().lower() not in ("false", "0", "no")


# Reporting


def describe() -> list[dict[str, Any]]:
    """Every variable with its effective value and its origin (env or default); tokens read set or unset."""
    rows: list[dict[str, Any]] = []

    def row(names: tuple[str, ...], value: str, default: str, secret: bool = False) -> None:
        origin = "env" if any(os.environ.get(n) for n in names) else "default"
        shown = ("set" if value else "unset") if secret else value
        rows.append({"variable": " or ".join(names), "value": shown, "origin": origin if not secret else ("env" if value else "unset"),
                     "default": "(none)" if secret or default == "" else default})

    row(("GOOGLE_CLOUD_PROJECT", "AIRLOCK_PROJECT"), project(), DEFAULT_PROJECT)
    row(("GOOGLE_CLOUD_LOCATION", "AIRLOCK_REGION"), region(), DEFAULT_REGION)
    row(("AIRLOCK_ASSETS_BUCKET",), bucket(), DEFAULT_BUCKET)
    row(("AGENT_ENGINE_RESOURCE",), engine_resource(), DEFAULT_ENGINE_RESOURCE)
    row(("AIRLOCK_RUNTIME",), runtime(), DEFAULT_RUNTIME)
    row(("GRAFANA_URL",), grafana_url(), DEFAULT_GRAFANA_URL)
    row(("GRAFANA_SERVICE_ACCOUNT_TOKEN",), grafana_service_account_token(), "", secret=True)
    row(("GRAFANA_PROM_UID",), prometheus_uid(), DEFAULT_PROM_UID)
    row(("GRAFANA_LOKI_UID",), loki_uid(), DEFAULT_LOKI_UID)
    row(("AIRLOCK_DASHBOARD_UID",), dashboard_uid(), DEFAULT_DASHBOARD_UID)
    row(("AIRLOCK_PUBLIC_DASHBOARD_URL",), public_dashboard_url(), DEFAULT_PUBLIC_DASHBOARD_URL)
    for ep in (influx(), loki()):
        row((f"{ep.name}_URL",), ep.url, "")
        row((f"{ep.name}_USER",), ep.user, "")
        row((f"{ep.name}_TOKEN",), ep.token, "", secret=True)
    row(("AIRLOCK_MCP_URL",), grafana_mcp_url(), DEFAULT_GRAFANA_MCP_URL)
    row(("AIRLOCK_MCP_TOKEN",), grafana_mcp_token(), "", secret=True)
    row(("AIRLOCK_MCP_SERVER_URL",), airlock_mcp_server_url(), DEFAULT_AIRLOCK_MCP_SERVER_URL)
    row(("AIRLOCK_MCP_SERVER_TOKEN",), airlock_mcp_server_token(), "", secret=True)
    row(("AIRLOCK_CONSOLE_URL",), console_url(), DEFAULT_CONSOLE_URL)
    row(("AIRLOCK_KEYCHAIN_ACCOUNT",), keychain_account(), DEFAULT_KEYCHAIN_ACCOUNT)
    row(("AIRLOCK_MUTE_GATE_TELEMETRY",), ",".join(sorted(muted_gates())), "")
    row(("AIRLOCK_INCIDENT_DRILL",), str(incident_drill()).lower(), str(DEFAULT_INCIDENT_DRILL).lower())
    return rows


# The Agent Engine deployment config, rendered from these settings so a judge on another project edits
# nothing by hand: `scripts/with_env.sh uv run python -m airlock.settings --render-engine-config`.

ENGINE_CONFIG_PATH = "agents/pipeline/.agent_engine_config.json"
ENGINE_EXTRA_PACKAGES = ["../../airlock", "../../charter.yaml", "../../rights-registry.yaml", "../../trust", "../../rules", "../../pricing.yaml"]
ENGINE_DESCRIPTION = ("Airlock: four gates in parallel, a verdict that asks Grafana before it rules, an investigator (gemini-2.5-flash) "
                      "that reads Loki and the alert rules and names the cause, an escalation that opens or joins the incident")
# Secret Manager names the deployed pipeline reads; the tokens never sit in the file.
ENGINE_SECRETS = {"AIRLOCK_MCP_TOKEN": "airlock-mcp-token", "GRAFANA_INFLUX_TOKEN": "grafana-influx-token", "GRAFANA_LOKI_TOKEN": "grafana-influx-token"}


def engine_config() -> dict[str, Any]:
    """The .agent_engine_config.json content from the current settings (env over defaults)."""
    env: dict[str, Any] = {
        "AIRLOCK_MCP_URL": grafana_mcp_url(),
        "AIRLOCK_DASHBOARD_UID": dashboard_uid(),
        "GRAFANA_URL": grafana_url(),
        "GRAFANA_PROM_UID": prometheus_uid(),
        "GRAFANA_LOKI_UID": loki_uid(),
        "AIRLOCK_RUNTIME": "agent-engine",
        "AIRLOCK_ASSETS_BUCKET": bucket(),
        "GRAFANA_INFLUX_URL": influx().url,
        "GRAFANA_INFLUX_USER": influx().user,
        "GRAFANA_LOKI_URL": loki().url,
        "GRAFANA_LOKI_USER": loki().user,
    }
    for var, secret in ENGINE_SECRETS.items():
        env[var] = {"secret": secret, "version": "latest"}
    env["AIRLOCK_PROJECT"] = project()
    return {"display_name": "airlock", "description": ENGINE_DESCRIPTION, "extra_packages": ENGINE_EXTRA_PACKAGES, "env_vars": env}


def render_engine_config(path: str = ENGINE_CONFIG_PATH) -> str:
    text = json.dumps(engine_config(), indent=2) + "\n"
    with open(path, "w") as f:
        f.write(text)
    return text


def main() -> None:
    if "--render-engine-config" in sys.argv:
        path = sys.argv[sys.argv.index("--render-engine-config") + 1] if len(sys.argv) > sys.argv.index("--render-engine-config") + 1 else ENGINE_CONFIG_PATH
        render_engine_config(path)
        print(f"wrote {path} from airlock.settings (env over defaults)")
        return
    for r in describe():
        print(f"{r['variable']:<48} {r['origin']:<8} {r['value']}")
    print(json.dumps({"defaults_from": "airlock/settings.py", "variables": len(describe())}))


if __name__ == "__main__":
    main()
