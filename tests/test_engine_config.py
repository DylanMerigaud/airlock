"""The Agent Engine config is rendered from airlock.settings: the committed file must equal the render under the
same environment, so a judge on another project changes settings, not JSON (second panel, 2026-09-05)."""

import json
import pathlib

from airlock import settings

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_committed_engine_config_matches_the_render(monkeypatch):
    committed = json.loads((REPO / settings.ENGINE_CONFIG_PATH).read_text())
    # The push endpoints have no defaults: the render needs the values the committed file carries.
    for var in ("GRAFANA_INFLUX_URL", "GRAFANA_INFLUX_USER", "GRAFANA_LOKI_URL", "GRAFANA_LOKI_USER"):
        monkeypatch.setenv(var, committed["env_vars"][var])
    for var in ("GOOGLE_CLOUD_PROJECT", "AIRLOCK_PROJECT", "AIRLOCK_ASSETS_BUCKET", "GRAFANA_URL", "GRAFANA_PROM_UID", "GRAFANA_LOKI_UID",
                "GRAFANA_TEMPO_UID", "AIRLOCK_DASHBOARD_UID", "AIRLOCK_MCP_URL", "GRAFANA_OTLP_URL", "GRAFANA_OTLP_USER"):
        monkeypatch.delenv(var, raising=False)
    assert settings.engine_config() == committed


def test_tokens_are_secret_references_never_values():
    cfg = settings.engine_config()
    for var in settings.ENGINE_SECRETS:
        assert set(cfg["env_vars"][var]) == {"secret", "version"}
    assert cfg["env_vars"]["GRAFANA_OTLP_TOKEN"]["secret"] == "grafana-traces-token"


def test_the_deployed_process_names_its_otel_resource():
    env = settings.engine_config()["env_vars"]
    assert env["OTEL_SERVICE_NAME"] == "airlock" and env["OTEL_RESOURCE_ATTRIBUTES"] == "deployment.environment=agent-engine"
    assert env["GRAFANA_OTLP_URL"].endswith("/otlp/v1/traces") and env["GRAFANA_OTLP_USER"] == "1811382"
