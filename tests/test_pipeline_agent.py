"""The pipeline's pure helpers: input options, the Loki answer parser, the Grafana wake retry. No cloud call."""

import asyncio
import json

import pytest

from agents.pipeline.agent import (
    GrafanaWaiter,
    injected_faults,
    loki_timestamp,
    looks_like_waking,
    muted_gates,
    parse_instant_value,
    parse_run_event,
)

RUN = "e-7f3a"


def loki_answer(*bodies: dict, labels_status: str = "PASS") -> str:
    rows = [{"timestamp": '"1788566913325404907"', "line": json.dumps(b), "labels": {"app": "airlock", "gate": "rights", "status": labels_status}}
            for b in bodies]
    return json.dumps({"data": rows, "metadata": {"linesReturned": len(rows)}})


def test_options_read_mute_and_fault_from_the_message_object():
    d = {"gcs_uri": "gs://b/x.mp4", "mute": ["rights"], "fault": {"rights": "timeout", "claim": None}}
    assert muted_gates(d) == ["rights"]
    assert injected_faults(d) == {"rights": "timeout"}
    assert muted_gates({}) == [] and injected_faults({}) == {}
    assert injected_faults({"fault": "timeout"}) == {}


def test_parse_run_event_takes_the_newest_line_of_this_run():
    text = loki_answer({"run_id": RUN, "status": "PASS", "asset_id": "a", "elapsed_ms": 3}, {"run_id": "e-old", "status": "ERROR"})
    ev = parse_run_event(text, RUN)
    assert ev is not None and ev["status"] == "PASS" and ev["elapsed_ms"] == 3
    assert ev["_timestamp"] == "2026-09-05T00:08:33.325Z"


def test_parse_run_event_skips_other_runs_and_empty_answers():
    assert parse_run_event(loki_answer({"run_id": "e-other", "status": "PASS"}), RUN) is None
    assert parse_run_event(json.dumps({"data": [], "hints": {"summary": "no entries"}}), RUN) is None
    assert parse_run_event("Loki query failed: (status 503): {}", RUN) is None


def test_parse_run_event_keeps_an_error_event_with_its_message():
    text = loki_answer({"run_id": RUN, "status": "ERROR", "reasons": ["TimeoutError: fault injected"], "fault": "timeout"}, labels_status="ERROR")
    ev = parse_run_event(text, RUN)
    assert ev is not None and ev["status"] == "ERROR" and ev["fault"] == "timeout"


def test_loki_timestamp_reads_the_quoted_nanoseconds():
    assert loki_timestamp('"1788566913325404907"') == "2026-09-05T00:08:33.325Z"
    assert loki_timestamp(None) is None
    assert loki_timestamp("not-a-number") == "not-a-number"


def test_parse_instant_value():
    assert parse_instant_value(json.dumps({"data": [{"metric": {}, "value": [1.0, "0.5"]}]})) == 0.5
    assert parse_instant_value(json.dumps({"data": []})) is None
    assert parse_instant_value("nope") is None
    assert parse_instant_value(json.dumps({"data": [{"value": [1.0, "NaN"]}]})) is None


def test_looks_like_waking_matches_the_measured_503_and_not_a_value_of_503():
    assert looks_like_waking("list datasources: [GET /datasources] getDataSources (status 503): {}")
    assert looks_like_waking('{"code":"Loading","message":"Your instance is loading, and will be ready shortly."}')
    assert looks_like_waking("ConnectError: connection refused")
    assert not looks_like_waking(json.dumps({"data": [{"metric": {}, "value": [1788566913.0, "503"]}]}))
    assert not looks_like_waking(json.dumps({"data": [{"metric": {}, "value": [1788566913.0, "503.2"]}]}))


def test_waiter_retries_while_grafana_wakes_and_records_the_wait():
    answers = iter(["getDataSources (status 503): {}", '{"code":"Loading"}', '{"data":[{"value":[1.0,"2"]}]}'])
    slept = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    async def call():
        return next(answers)

    waiter = GrafanaWaiter(retry_s=10, budget_s=180, sleep=fake_sleep)
    text = asyncio.run(waiter.call(call))
    assert text == '{"data":[{"value":[1.0,"2"]}]}'
    assert slept == [10, 10] and waiter.waited_s == 20 and waiter.attempts == 3


def test_waiter_retries_on_a_waking_exception_and_re_raises_the_others():
    calls = {"n": 0}

    async def fake_sleep(s: float) -> None:
        return None

    async def refused_then_ok():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("connection refused")
        return "ok"

    waiter = GrafanaWaiter(retry_s=1, budget_s=60, sleep=fake_sleep)
    assert asyncio.run(waiter.call(refused_then_ok)) == "ok" and waiter.waited_s == 1

    async def broken():
        raise ValueError("bad args")

    with pytest.raises(ValueError, match="bad args"):
        asyncio.run(GrafanaWaiter(sleep=fake_sleep).call(broken))


def test_waiter_gives_up_after_the_budget():
    async def fake_sleep(s: float) -> None:
        return None

    async def still_loading():
        return "(status 503): {}"

    waiter = GrafanaWaiter(retry_s=10, budget_s=0, sleep=fake_sleep)
    with pytest.raises(RuntimeError, match="Grafana Cloud still starting after 0 s"):
        asyncio.run(waiter.call(still_loading))
