"""Dotmac integration client — canonical inter-service HTTP transport.

Import name is ``dotmac_integration_client``. It is deliberately NOT
``dotmac_integration``: that top-level name belongs to the Starter's published
``dotmac-integration`` module (the connector control plane), and two
distributions claiming one import package makes the winner install-order
dependent. See CHANGELOG 0.2.0.
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
