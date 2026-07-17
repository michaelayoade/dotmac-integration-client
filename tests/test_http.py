"""Behavioural tests for the canonical integration transport."""

from __future__ import annotations

import httpx
import pytest

from dotmac_integration import (
    IntegrationHttpClient,
    ReachabilityCircuit,
    exponential_backoff,
)


class _Transient(Exception):
    pass


class _RateLimited(Exception):
    retry_after = 0.0


class _Fatal(Exception):
    pass


class _FakeResponse:
    def __init__(self, status_code: int, body=None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


class _FakeClient:
    """Scripted responses/exceptions per attempt."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


def _handler(response):
    if response.status_code == 429:
        raise _RateLimited()
    if response.status_code >= 500:
        raise _Transient()
    if response.status_code >= 400:
        raise _Fatal()
    return response.json()


def _client(fake, **overrides):
    kwargs = dict(
        client_factory=lambda: fake,
        response_handler=_handler,
        backoff=lambda attempt: 0.0,
        max_attempts=3,
        rate_limit_exc=_RateLimited,
        retryable_excs=(_Transient,),
        non_retryable_excs=(_Fatal,),
    )
    kwargs.update(overrides)
    return IntegrationHttpClient(**kwargs)


def test_retries_transient_then_succeeds():
    fake = _FakeClient([_FakeResponse(503), _FakeResponse(200, {"ok": True})])
    assert _client(fake).request("GET", "/x") == {"ok": True}
    assert len(fake.calls) == 2


def test_non_retryable_raises_immediately():
    fake = _FakeClient([_FakeResponse(403)])
    with pytest.raises(_Fatal):
        _client(fake).request("GET", "/x")
    assert len(fake.calls) == 1


def test_transient_exhaustion_reraises():
    fake = _FakeClient([_FakeResponse(500)] * 3)
    with pytest.raises(_Transient):
        _client(fake).request("GET", "/x")
    assert len(fake.calls) == 3


def test_request_id_propagates_without_clobbering_caller():
    fake = _FakeClient([_FakeResponse(200)])
    _client(fake, request_id_provider=lambda: "rid-123").request("GET", "/x")
    assert fake.calls[0]["headers"]["x-request-id"] == "rid-123"

    fake2 = _FakeClient([_FakeResponse(200)])
    _client(fake2, request_id_provider=lambda: "rid-123").request(
        "GET", "/x", headers={"X-Request-Id": "caller-wins"}
    )
    sent = fake2.calls[0]["headers"]
    assert sent.get("X-Request-Id") == "caller-wins"
    assert "x-request-id" not in sent


def test_observer_sees_success_and_transport_error():
    seen: list[dict] = []

    def observer(**kw):
        seen.append(kw)

    fake = _FakeClient([httpx.ConnectError("boom"), _FakeResponse(200, {"ok": 1})])
    _client(fake, observer=observer, edge="testedge").request("GET", "/x")
    assert seen[0]["error"] is not None and seen[0]["status"] is None
    assert seen[1]["status"] == 200 and seen[1]["edge"] == "testedge"


def test_observer_failure_never_breaks_the_edge():
    def bad_observer(**kw):
        raise RuntimeError("metrics down")

    fake = _FakeClient([_FakeResponse(200, {"ok": 1})])
    assert _client(fake, observer=bad_observer).request("GET", "/x") == {"ok": 1}


def test_circuit_trips_on_transport_and_blocks():
    circuit = ReachabilityCircuit(cooldown_seconds=60)
    fake = _FakeClient([httpx.ConnectError("down")] * 3)
    client = _client(fake, circuit=circuit)
    with pytest.raises(httpx.ConnectError):
        client.request("GET", "/x")
    assert circuit.is_open()
    with pytest.raises(RuntimeError):
        client.request("GET", "/x")
    assert len(fake.calls) == 3  # no request while open


def test_exponential_backoff_jitters_within_bounds():
    backoff = exponential_backoff(base=1.0, cap=8.0, jitter=0.25)
    for attempt, floor in ((0, 1.0), (1, 2.0), (2, 4.0), (5, 8.0)):
        value = backoff(attempt)
        assert floor <= value <= floor + 0.25


def test_rate_limit_honours_retry_after_then_succeeds():
    fake = _FakeClient([_FakeResponse(429), _FakeResponse(200, {"ok": 1})])
    assert _client(fake).request("GET", "/x") == {"ok": 1}
    assert len(fake.calls) == 2


def test_idempotency_key_header():
    fake = _FakeClient([_FakeResponse(200)])
    _client(fake).request("POST", "/x", idempotency_key="k-1")
    assert fake.calls[0]["headers"]["Idempotency-Key"] == "k-1"
