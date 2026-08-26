# Changelog

All notable changes to `dotmac-integration-client`.

## 0.2.0 — 2026-08-14

### Breaking — the import package is renamed

`dotmac_integration` → **`dotmac_integration_client`**.

Nothing about the behaviour, the public API, or the transport policy engine
changed. The only change is the top-level import name, and it is breaking for
every consumer.

**Why.** Through v0.1.1 this distribution declared
`packages = [{ include = "dotmac_integration", from = "src" }]`. That top-level
import name is already owned by a different Dotmac distribution: the Starter's
published `dotmac-integration` module
(`dotmac_starter_mt/packages/dotmac-integration/`), the external connector
control plane — installations, configuration revisions, capability bindings,
the connector SPI, its own `mod_ig` Alembic lineage. Two distributions claiming
one top-level package is not a namespace package and does not merge: whichever
is installed last wins the directory on `sys.path`, and `import dotmac_integration`
silently resolves to it. An app that pins both (any app that runs a connector
runtime *and* talks over an integration edge) gets an `ImportError` on
`IntegrationHttpClient` — or, worse, a working import today that breaks on an
unrelated reinstall.

The two artifacts are genuinely different things and neither should yield its
identity to install order:

| distribution | import | owns |
| --- | --- | --- |
| `dotmac-integration` (Starter module) | `dotmac_integration` | connector control plane — installations, revisions, bindings, SPI, dispatch |
| `dotmac-integration-client` (this) | `dotmac_integration_client` | HTTP transport policy engine for an integration edge |

This package is the newer claimant on a name the module already published, so
this package moves.

### What consumers must do

1. Bump the pin to `tag = "v0.2.0"`.
2. Rewrite every import:

   ```diff
   -from dotmac_integration import IntegrationHttpClient
   +from dotmac_integration_client import IntegrationHttpClient
   ```

   The four exported names are unchanged: `IntegrationHttpClient`,
   `ReachabilityCircuit`, `exponential_backoff`, `CircuitBreaker`.
3. Re-lock (`poetry lock --no-update` then `poetry install`).

There is deliberately **no** `dotmac_integration` compatibility shim. A shim
would re-create the exact collision this release exists to remove — it would
still install a top-level `dotmac_integration` and still shadow the Starter
module. A failed import at deploy time is the correct, loud outcome; a silently
shadowed control plane is not.

Known consumers requiring the edit (as of this release): `dotmac_sub`
(`app/services/crm_client.py`, `app/services/dotmac_erp/client.py`) and
`dotmac_erp` (`app/services/dotmac_sub/client.py`, `app/services/crm/client.py`).

## 0.1.1

- `observer` tolerates non-`Response` returns from client factories.

## 0.1.0

- Initial canonical Dotmac integration HTTP transport: bounded retry with
  jittered exponential backoff, `Retry-After` honouring on 429,
  transient-vs-fatal classification driven by the edge's own exception types,
  optional `ReachabilityCircuit`, `Idempotency-Key`, `x-request-id`
  propagation, and a best-effort metrics observer hook.
