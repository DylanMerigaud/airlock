"""airlock.gemini.ask_json: an answer with no text names the refusal instead of failing on json.loads(None)."""

from types import SimpleNamespace

import pytest

from airlock import gemini


class FakeModels:
    def __init__(self, resp):
        self.resp = resp

    def generate_content(self, **kwargs):
        return self.resp


def enum(name: str):
    return SimpleNamespace(name=name)


def test_ask_json_names_the_safety_block(monkeypatch):
    rating = SimpleNamespace(category=enum("HARM_CATEGORY_SEXUALLY_EXPLICIT"), probability=enum("HIGH"), blocked=True)
    candidate = SimpleNamespace(finish_reason=enum("SAFETY"), finish_message=None, safety_ratings=[rating])
    resp = SimpleNamespace(text=None, candidates=[candidate], prompt_feedback=None, usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=0))
    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=FakeModels(resp)))
    with pytest.raises(RuntimeError) as exc:
        gemini.ask_json("gemini-2.5-flash", [], {"type": "object"})
    message = str(exc.value)
    assert "gemini-2.5-flash returned no text" in message
    assert "finish reason SAFETY" in message and "HARM_CATEGORY_SEXUALLY_EXPLICIT=HIGH" in message
    assert "JSON object must be str" not in message


def test_ask_json_names_a_blocked_prompt(monkeypatch):
    feedback = SimpleNamespace(block_reason=enum("PROHIBITED_CONTENT"), block_reason_message="prohibited")
    resp = SimpleNamespace(text=None, candidates=[], prompt_feedback=feedback, usage_metadata=None)
    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=FakeModels(resp)))
    with pytest.raises(RuntimeError, match="prompt blocked"):
        gemini.ask_json("gemini-2.5-pro", [], {"type": "object"})


def test_ask_json_parses_a_normal_answer(monkeypatch):
    resp = SimpleNamespace(text='{"claims": []}', candidates=[], prompt_feedback=None, usage_metadata=SimpleNamespace(prompt_token_count=5, candidates_token_count=3))
    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=FakeModels(resp)))
    answer, usage = gemini.ask_json("gemini-2.5-pro", [], {"type": "object"})
    assert answer == {"claims": []} and usage == {"model": "gemini-2.5-pro", "prompt_tokens": 5, "output_tokens": 3}
