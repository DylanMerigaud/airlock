"""airlock.settings: one place for the coordinates, read at call time, defaults as this deployment's values."""

from airlock import settings
from airlock.gates import CHECKS, GATES


def test_defaults_are_this_deployment(monkeypatch):
    for name in ("GOOGLE_CLOUD_PROJECT", "AIRLOCK_PROJECT", "AIRLOCK_ASSETS_BUCKET", "AGENT_ENGINE_RESOURCE", "AIRLOCK_KEYCHAIN_ACCOUNT",
                 "GRAFANA_URL", "AIRLOCK_DASHBOARD_UID", "AIRLOCK_MCP_URL", "AIRLOCK_MCP_SERVER_URL", "AIRLOCK_CONSOLE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert settings.project() == "airlock-agentic-cinema"
    assert settings.bucket() == "airlock-agentic-cinema-assets"
    assert settings.engine_resource().endswith("/reasoningEngines/1737023312967499776")
    assert settings.keychain_account() == "dylanmerigaud"
    assert settings.grafana_url() == "https://narrowsubmarine1895.grafana.net"
    assert settings.dashboard_uid() == "airlock-gates"
    assert settings.grafana_mcp_url().endswith(".run.app/mcp") and "mcp-grafana" in settings.grafana_mcp_url()
    assert settings.airlock_mcp_server_url().endswith(".run.app/mcp") and "airlock-mcp-7" in settings.airlock_mcp_server_url()


def test_env_wins_and_is_read_at_call_time(monkeypatch):
    monkeypatch.setenv("AIRLOCK_PROJECT", "judge-project")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    assert settings.project() == "judge-project"
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "sdk-project")  # what the Google SDKs read comes first
    assert settings.project() == "sdk-project"
    monkeypatch.setenv("AIRLOCK_ASSETS_BUCKET", "judge-bucket")
    assert settings.bucket() == "judge-bucket"
    monkeypatch.setenv("AIRLOCK_KEYCHAIN_ACCOUNT", "someone")
    assert settings.keychain_account() == "someone"
    monkeypatch.setenv("GRAFANA_URL", "https://x.grafana.net/")
    assert settings.grafana_url() == "https://x.grafana.net"


def test_an_empty_datasource_uid_means_ask(monkeypatch):
    monkeypatch.setenv("GRAFANA_PROM_UID", "")
    monkeypatch.delenv("GRAFANA_LOKI_UID", raising=False)
    assert settings.prometheus_uid() == ""
    assert settings.loki_uid() == "grafanacloud-logs"


def test_telemetry_endpoints_have_no_default(monkeypatch):
    for name in ("GRAFANA_INFLUX_URL", "GRAFANA_INFLUX_USER", "GRAFANA_INFLUX_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    ep = settings.influx()
    assert not ep.configured and ep.missing() == ["GRAFANA_INFLUX_URL", "GRAFANA_INFLUX_USER", "GRAFANA_INFLUX_TOKEN"]
    monkeypatch.setenv("GRAFANA_INFLUX_URL", "https://influx.example/write")
    monkeypatch.setenv("GRAFANA_INFLUX_USER", "1")
    assert settings.influx().configured and settings.influx().missing() == ["GRAFANA_INFLUX_TOKEN"]


def test_the_traces_endpoint_defaults_the_gateway_and_never_the_token(monkeypatch):
    for name in ("GRAFANA_OTLP_URL", "GRAFANA_OTLP_USER", "GRAFANA_OTLP_TOKEN", "GRAFANA_TEMPO_UID"):
        monkeypatch.delenv(name, raising=False)
    ep = settings.otlp()
    assert ep.url == "https://otlp-gateway-prod-us-west-0.grafana.net/otlp/v1/traces" and ep.user == "1811382"
    assert ep.missing() == ["GRAFANA_OTLP_TOKEN"]
    assert settings.tempo_uid() == "grafanacloud-traces"
    monkeypatch.setenv("GRAFANA_OTLP_TOKEN", "t")
    monkeypatch.setenv("GRAFANA_OTLP_URL", "")
    assert settings.otlp().missing() == ["GRAFANA_OTLP_URL"] and not settings.otlp().configured
    rows = {r["variable"]: r for r in settings.describe()}
    assert rows["GRAFANA_OTLP_TOKEN"]["value"] == "set" and rows["GRAFANA_OTLP_USER"]["origin"] == "default"


def test_incident_drill_switch(monkeypatch):
    monkeypatch.delenv("AIRLOCK_INCIDENT_DRILL", raising=False)
    assert settings.incident_drill() is True
    monkeypatch.setenv("AIRLOCK_INCIDENT_DRILL", "false")
    assert settings.incident_drill() is False
    monkeypatch.setenv("AIRLOCK_INCIDENT_DRILL", "true")
    assert settings.incident_drill() is True


def test_describe_never_prints_a_token(monkeypatch):
    monkeypatch.setenv("GRAFANA_INFLUX_TOKEN", "s3cret-value")
    monkeypatch.setenv("AIRLOCK_MCP_SERVER_TOKEN", "another-s3cret")
    rows = settings.describe()
    text = " ".join(f"{r['variable']} {r['value']} {r['default']}" for r in rows)
    assert "s3cret" not in text
    tokens = {r["variable"]: r["value"] for r in rows if "TOKEN" in r["variable"]}
    assert tokens["GRAFANA_INFLUX_TOKEN"] == "set" and tokens["AIRLOCK_MCP_SERVER_TOKEN"] == "set"


def test_the_one_checks_table_names_every_gate_in_order():
    assert tuple(CHECKS) == GATES == ("rights", "claim", "brand", "provenance")
    for gate, (fn, source) in CHECKS.items():
        assert callable(fn) and fn.__module__ == f"airlock.gates.{gate}"
        assert source and isinstance(source, str)
