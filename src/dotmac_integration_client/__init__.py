"""Dotmac integration client — canonical inter-service HTTP transport.

The import name is deliberately not ``dotmac_integration``. That top-level
package belongs to Starter's published connector-control-plane module; two
distributions claiming it make the winner install-order dependent.
"""

from dotmac_integration_client.http import (
    CircuitBreaker,
    IntegrationHttpClient,
    ReachabilityCircuit,
    exponential_backoff,
)

__all__ = [
    "CircuitBreaker",
    "IntegrationHttpClient",
    "ReachabilityCircuit",
    "exponential_backoff",
]
__version__ = "0.2.0"
