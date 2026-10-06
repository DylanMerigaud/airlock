"""The gates' Gemini client goes to the global endpoint unless AIRLOCK_GEMINI_LOCATION says otherwise."""

from airlock import gemini, settings


def test_default_is_the_global_endpoint_whatever_the_runtime_region(monkeypatch):
    monkeypatch.delenv("AIRLOCK_GEMINI_LOCATION", raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")  # what Agent Engine sets for its own region
    assert settings.gemini_location() == "global"
    assert settings.region() == "us-central1"


def test_env_overrides_the_location(monkeypatch):
    monkeypatch.setenv("AIRLOCK_GEMINI_LOCATION", "europe-west4")
    assert settings.gemini_location() == "europe-west4"


def test_the_client_is_built_with_the_gemini_location(monkeypatch):
    seen: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(gemini, "_client", None)
    monkeypatch.setattr(gemini.genai, "Client", FakeClient)
    monkeypatch.delenv("AIRLOCK_GEMINI_LOCATION", raising=False)
    try:
        gemini.client()
    finally:
        monkeypatch.setattr(gemini, "_client", None)
    assert seen["location"] == "global" and seen["vertexai"] is True
