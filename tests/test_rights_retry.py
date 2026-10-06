"""A stalled Video Intelligence operation is replaced by a fresh one; two stalls are an ERROR that names both."""

import pytest

from airlock.gates.rights import await_annotation


class FakeOp:
    def __init__(self, answer=None, stalls=False, cancel_fails=False):
        self.answer, self.stalls, self.cancel_fails = answer, stalls, cancel_fails
        self.timeouts: list[float] = []
        self.cancelled = False

    def result(self, timeout):
        self.timeouts.append(timeout)
        if self.stalls:
            raise TimeoutError(f"Operation did not complete within the designated timeout of {timeout} seconds.")
        return self.answer

    def cancel(self):
        self.cancelled = True
        if self.cancel_fails:
            raise RuntimeError("operation already gone")


class FakeClient:
    def __init__(self, ops):
        self.ops = list(ops)
        self.started: list[dict] = []

    def annotate_video(self, request):
        self.started.append(request)
        return self.ops.pop(0)


def test_a_stalled_operation_is_cancelled_and_replaced(monkeypatch):
    monkeypatch.delenv("AIRLOCK_VI_TIMEOUT_S", raising=False)
    monkeypatch.delenv("AIRLOCK_VI_ATTEMPTS", raising=False)
    stalled, fresh = FakeOp(stalls=True), FakeOp(answer="annotations")
    client = FakeClient([stalled, fresh])
    assert await_annotation(client, {"input_uri": "gs://b/clip.mp4"}) == "annotations"
    assert stalled.cancelled and not fresh.cancelled
    assert stalled.timeouts == [240.0] and fresh.timeouts == [240.0]
    assert client.started == [{"input_uri": "gs://b/clip.mp4"}] * 2


def test_two_stalls_raise_naming_the_attempts_and_the_next_attempt_still_starts_when_a_cancel_fails(monkeypatch):
    monkeypatch.setenv("AIRLOCK_VI_TIMEOUT_S", "7")
    monkeypatch.setenv("AIRLOCK_VI_ATTEMPTS", "2")
    first, second = FakeOp(stalls=True, cancel_fails=True), FakeOp(stalls=True)
    client = FakeClient([first, second])
    with pytest.raises(TimeoutError, match=r"no answer in 7 s on each of 2 attempt\(s\)"):
        await_annotation(client, {})
    assert first.cancelled and second.cancelled
    assert len(client.started) == 2


def test_an_answer_on_the_first_attempt_starts_one_operation(monkeypatch):
    monkeypatch.delenv("AIRLOCK_VI_TIMEOUT_S", raising=False)
    monkeypatch.delenv("AIRLOCK_VI_ATTEMPTS", raising=False)
    op = FakeOp(answer="annotations")
    client = FakeClient([op])
    assert await_annotation(client, {}) == "annotations"
    assert len(client.started) == 1 and not op.cancelled
