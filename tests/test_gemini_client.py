"""The shared Gemini client carries a finite request timeout (an eval run hung 32 minutes on 2026-09-05 without one)."""
from unittest import mock

import airlock.gemini as gemini


def test_client_is_built_with_a_finite_timeout(monkeypatch):
    monkeypatch.setattr(gemini, "_client", None)
    monkeypatch.setenv("AIRLOCK_GEMINI_TIMEOUT_MS", "1234")
    with mock.patch.object(gemini.genai, "Client") as ctor:
        gemini.client()
    kwargs = ctor.call_args.kwargs
    assert kwargs["http_options"].timeout == 1234
    monkeypatch.setattr(gemini, "_client", None)
