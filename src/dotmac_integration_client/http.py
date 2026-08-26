"""Canonical HTTP transport for Dotmac inter-service integration edges.

Every integration edge (crm→erp, crm→sub, sub→crm, sub→erp, erp→sub, erp→crm,
and future apps) needs the same transport plumbing: a bounded retry loop with
jittered backoff, Retry-After honouring, an optional reachability circuit
breaker, auth-header injection, idempotency keys, request-id propagation, and
metrics. This package centralises that loop so each edge only declares its
*policy* — which exceptions retry, how a response maps to a parsed body or a
typed error — while keeping its own public API and exception types.

Design: the caller supplies a ``client_factory`` (a callable returning a pooled
``httpx.Client``) and a ``response_handler`` (maps a response to a parsed body
or raises the edge's typed error). Retry classification is driven by the
exception types the handler raises, so the edge's error hierarchy is preserved
verbatim.

v2 additions over the previously-vendored copies (dotmac_crm / dotmac_sub):
``exponential_backoff`` with jitter, ``ReachabilityCircuit`` (the reference
breaker both repos hand-rolled), ``request_id_provider`` (propagates
``x-request-id`` so traces survive hops), and ``observer`` (a metrics hook in
the shape of ERP's ``observe_integration_request``).
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

# Transport-level failures that always warrant a retry (peer slow/unreachable).
_TRANSPORT_EXCS: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.TimeoutException,
)


class CircuitBreaker(Protocol):
    """A short-cooldown reachability breaker (trip on transport failure)."""

    def is_open(self) -> bool: ...

    def trip(self) -> None: ...

    def reset(self) -> None: ...


class ReachabilityCircuit:
    """Reference short-cooldown breaker: trip on transport failure, auto-close.

    Thread-safe; ``cooldown_seconds <= 0`` disables it (never open).
    """

    def __init__(self, cooldown_seconds: float = 30.0) -> None:
        self._cooldown = float(cooldown_seconds)
        self._open_until = 0.0
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        if self._cooldown <= 0:
            return False
        with self._lock:
            return time.monotonic() < self._open_until

    def trip(self) -> None:
        if self._cooldown <= 0:
            return
        with self._lock:
            self._open_until = time.monotonic() + self._cooldown

    def reset(self) -> None:
        with self._lock:
            self._open_until = 0.0


def exponential_backoff(
    base: float = 0.5,
    cap: float = 30.0,
    jitter: float = 0.25,
) -> Callable[[int], float]:
    """Jittered exponential backoff: ``min(cap, base * 2**attempt) + U(0, jitter)``.

    Jitter decorrelates retry storms across concurrent callers — the property
    only one of the six pre-package edges actually had.
    """

    def _backoff(attempt: int) -> float:
        return min(cap, base * (2**attempt)) + random.uniform(0.0, jitter)

    return _backoff


class IntegrationHttpClient:
    """Reusable retry/transport engine for a single integration edge.

    Parameters describe the edge's policy:

    - ``client_factory``: returns a (pooled) ``httpx.Client`` — called once per
      request, reused across that request's retry attempts.
    - ``response_handler(response, **handler_kwargs)``: returns the parsed body
      or raises the edge's typed error. Retry behaviour keys off those types.
    - ``backoff(attempt)``: seconds to sleep before the next attempt (0-indexed).
    - ``max_attempts``: total attempts (initial + retries).
    - ``rate_limit_exc``: raised on 429; its ``retry_after`` attribute (if set)
      overrides the backoff. Retried every attempt.
    - ``retryable_excs``: retried up to the cap, then re-raised as-is (e.g. a
      transient-5xx type).
    - ``non_retryable_excs``: raised immediately (e.g. auth / generic 4xx).
    - ``transport_exhausted_factory(exc, retries)`` / ``loop_exhausted_factory``
      / ``unexpected_error_factory``: wrap the give-up / unexpected cases in the
      edge's error type.
    - ``circuit``: tripped on a transport failure, reset on any response.
    """

    def __init__(
        self,
        *,
        client_factory: Callable[[], Any],
        response_handler: Callable[..., Any],
        backoff: Callable[[int], float],
        max_attempts: int,
        rate_limit_exc: type[BaseException] | None = None,
        retryable_excs: tuple[type[BaseException], ...] = (),
        non_retryable_excs: tuple[type[BaseException], ...] = (),
        transport_exhausted_factory: Callable[[BaseException, int], BaseException]
        | None = None,
        loop_exhausted_factory: Callable[[BaseException, int], BaseException]
        | None = None,
        unexpected_error_factory: Callable[[BaseException], BaseException]
        | None = None,
        circuit: CircuitBreaker | None = None,
        auth_headers: Callable[[], dict[str, str]] | dict[str, str] | None = None,
        edge: str = "integration",
        request_id_provider: Callable[[], str | None] | None = None,
        observer: Callable[..., None] | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._response_handler = response_handler
        self._backoff = backoff
        self._max_attempts = max(1, max_attempts)
        self._rate_limit_exc = rate_limit_exc
        self._retryable_excs = retryable_excs
        self._non_retryable_excs = non_retryable_excs
        self._transport_exhausted_factory = transport_exhausted_factory
        self._loop_exhausted_factory = loop_exhausted_factory
        self._unexpected_error_factory = unexpected_error_factory
        self._circuit = circuit
        self._auth_headers = auth_headers
        self._edge = edge
        self._request_id_provider = request_id_provider
        self._observer = observer

    def _base_headers(self) -> dict[str, str]:
        if callable(self._auth_headers):
            return dict(self._auth_headers())
        return dict(self._auth_headers or {})

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: Any = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
        handler_kwargs: dict[str, Any] | None = None,
    ) -> Any:
        if self._circuit is not None and self._circuit.is_open():
            raise self._circuit_open_error(path)

        req_headers = self._base_headers()
        if headers:
            req_headers.update(headers)
        if self._request_id_provider is not None:
            request_id = self._request_id_provider()
            if request_id and "x-request-id" not in {k.lower() for k in req_headers}:
                req_headers["x-request-id"] = request_id
        if idempotency_key:
            req_headers["Idempotency-Key"] = idempotency_key
        handler_kwargs = handler_kwargs or {}

        client = self._client_factory()
        retries = self._max_attempts - 1
        last_error: BaseException | None = None

        for attempt in range(self._max_attempts):
            started = time.monotonic()
            try:
                response = client.request(
                    method=method,
                    url=path,
                    params=params,
                    json=json_data,
                    headers=req_headers or None,
                )
                if self._circuit is not None:
                    self._circuit.reset()
                self._observe(
                    method, path, getattr(response, "status_code", None), started
                )
                return self._response_handler(response, **handler_kwargs)
            except BaseException as exc:
                last_error = exc
                if isinstance(exc, _TRANSPORT_EXCS):
                    self._observe(method, path, None, started, error=exc)
                # Order matters: rate-limit and retryable/transient subtypes are
                # checked before the broader non-retryable set they may inherit.
                if self._rate_limit_exc is not None and isinstance(
                    exc, self._rate_limit_exc
                ):
                    delay = getattr(exc, "retry_after", None) or self._backoff(attempt)
                    logger.warning(
                        "integration rate-limited on %s, waiting %.1fs (attempt %d/%d)",
                        path,
                        delay,
                        attempt + 1,
                        self._max_attempts,
                    )
                    time.sleep(delay)
                    continue
                if isinstance(exc, _TRANSPORT_EXCS):
                    if self._circuit is not None:
                        self._circuit.trip()
                    if attempt < retries:
                        time.sleep(self._backoff(attempt))
                        continue
                    if self._transport_exhausted_factory is not None:
                        raise self._transport_exhausted_factory(exc, retries) from exc
                    raise
                if self._retryable_excs and isinstance(exc, self._retryable_excs):
                    if attempt < retries:
                        time.sleep(self._backoff(attempt))
                        continue
                    raise
                if self._non_retryable_excs and isinstance(
                    exc, self._non_retryable_excs
                ):
                    raise
                if self._unexpected_error_factory is not None:
                    raise self._unexpected_error_factory(exc) from exc
                raise

        # Only reached when the rate-limit path exhausts every attempt.
        if last_error is not None and self._loop_exhausted_factory is not None:
            raise self._loop_exhausted_factory(last_error, retries)
        if last_error is not None:
            raise last_error
        return None

    def _observe(
        self,
        method: str,
        path: str,
        status: int | None,
        started: float,
        error: BaseException | None = None,
    ) -> None:
        """Best-effort metrics hook — never lets observability break the edge."""
        if self._observer is None:
            return
        try:
            self._observer(
                edge=self._edge,
                method=method,
                path=path,
                status=status,
                duration_seconds=time.monotonic() - started,
                error=error,
            )
        except Exception:  # pragma: no cover - observability must not raise
            logger.debug("integration observer failed", exc_info=True)

    def _circuit_open_error(self, path: str) -> BaseException:
        if self._loop_exhausted_factory is not None:
            return self._loop_exhausted_factory(
                RuntimeError(f"circuit open for {path}"), 0
            )
        return RuntimeError(
            f"integration temporarily unavailable (circuit open) for {path}"
        )
