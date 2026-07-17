# dotmac-integration-client

Canonical HTTP transport for Dotmac inter-service integration edges
(crm↔sub↔erp and future apps: field, academy, omni…).

Each edge keeps its own public API and typed error hierarchy; this package owns
the transport *policy engine*: bounded retry with jittered exponential backoff,
`Retry-After` honouring on 429, transient-vs-fatal classification driven by the
edge's exception types, an optional reachability circuit breaker,
`Idempotency-Key` on writes, `x-request-id` propagation (so traces survive
hops), and a best-effort metrics observer hook.

## Install (per app, pinned git dependency)

```toml
[tool.poetry.dependencies]
dotmac-integration-client = { git = "https://github.com/michaelayoade/dotmac-integration-client.git", tag = "v0.1.0" }
```

## Usage sketch

```python
from dotmac_integration import (
    IntegrationHttpClient, ReachabilityCircuit, exponential_backoff,
)

engine = IntegrationHttpClient(
    client_factory=get_pooled_httpx_client,
    response_handler=parse_or_raise_edge_error,
    backoff=exponential_backoff(base=0.5, cap=30.0),
    max_attempts=4,
    rate_limit_exc=EdgeRateLimitError,        # honours .retry_after
    retryable_excs=(EdgeTransientError,),
    non_retryable_excs=(EdgeAuthError, EdgeClientError),
    circuit=ReachabilityCircuit(cooldown_seconds=30),
    auth_headers=lambda: {"X-Api-Key": resolve_key()},
    edge="dotmac_sub",
    request_id_provider=current_request_id,   # your app's contextvar
    observer=observe_integration_request,     # your app's metrics fn
)
```

The engine never invents policy: what retries, what maps to which error, and
what the edge is called are all declared by the consuming app.
