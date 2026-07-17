"""Dotmac integration client — canonical inter-service HTTP transport."""

from dotmac_integration.http import (
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
__version__ = "0.1.1"
