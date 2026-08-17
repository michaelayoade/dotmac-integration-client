# Changelog

All notable changes to `dotmac-integration-client`.

## 0.2.0 — 2026-08-17

### Breaking — the import package is renamed

`dotmac_integration` → **`dotmac_integration_client`**.

Transport behavior and the four-name public API are unchanged. The import name
changes for every consumer because v0.1.1 collided with Starter's published
`dotmac-integration` control-plane module. Both distributions installed one
top-level `dotmac_integration` package, so import resolution depended on install
order.

| distribution | import | owner |
| --- | --- | --- |
| `dotmac-integration` | `dotmac_integration` | Connector registry, execution, evidence, and `mod_intg` lineage |
| `dotmac-integration-client` | `dotmac_integration_client` | HTTP transport policy for an application integration edge |

This package is the newer claimant and therefore moves. There is deliberately no
compatibility shim: shipping one would recreate the collision this release
removes.

Consumers must pin `v0.2.0`, rewrite their imports, run the repository-owned
`poetry lock`, and validate the resulting environment. Known consumers at this
release are:

- `dotmac_sub`: `app/services/crm_client.py`,
  `app/services/dotmac_erp/client.py`;
- `dotmac_erp`: `app/services/crm/client.py`,
  `app/services/dotmac_sub/client.py`.

## 0.1.1

- The observer tolerates non-`Response` returns from client factories.

## 0.1.0

- Initial bounded HTTP retry transport with jitter, `Retry-After`, reachability
  circuit, idempotency keys, request-id propagation, and observer hooks.
