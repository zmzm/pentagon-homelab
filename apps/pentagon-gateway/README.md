# Pentagon Gateway

Pentagon Gateway is the Hermes tool gateway. FlowForge is the separate task runner;
its workflow API and tool names retain their existing names.

Portable REST boundary for Knowledge Router, existing FlowForge workflows and constrained
Docker operations. Uses the Node.js 24+ standard library at runtime. Hermes connects through the
thin MCP adapter in `../hermes/gateway_mcp.py`; other runtimes can use the same HTTP API.

See [deployment, API, policy and acceptance documentation](../hermes/README.md).

## Development

Run these commands from `apps/pentagon-gateway` with Node.js 24+ and npm:

```bash
npm ci
npm run check
```

`check` runs [ESLint](https://eslint.org/docs/latest/use/configure/configuration-files),
[Prettier's format check](https://prettier.io/docs/configuration), and the existing
`node:test` suite.
Use `npm run lint:fix` and `npm run format` to apply fixes, then review the diff.
`npm test` still runs without installing development tools. Tests use local HTTP
and Unix sockets and temporary files; real retrieval cases also need the external
Knowledge Router checkout and report skips when it is unavailable. These checks
do not exercise deployed services.

The app's conventions are:

- Keep ESM `.mjs` modules, explicit relative import extensions, `node:` imports for
  built-ins, and `node:test` tests. ESLint uses Node globals, not browser or CommonJS
  globals, for all JavaScript files.
- Use Prettier's two-space indentation, semicolons, single quotes, and a 100-column
  wrapping target. Let the formatter lay out request objects and long expressions.
- Use braces for every control-flow body, one variable declaration per statement,
  `const` for bindings that are not reassigned, and strict equality. ESLint's
  recommended correctness rules also reject unused bindings and undefined names.
  Prefix intentionally discarded variable bindings with `_`; ESLint rejects using
  those bindings later.
- Preserve HTTP/tool field names and persisted record shapes when naming local
  variables. Keep gateway authorization in `server.mjs`/`operations.mjs`, Docker
  operations in `broker.mjs`, and Matrix delivery in the relay modules.

For naming, readable decisions, and module extraction, follow the shared
`common/engineering/references/readability-and-boundaries.md` reference after
resolving the coding root through the
[repository procedure](../../docs/engineering.md#shared-guidance-and-provenance).
Use the existing behavior tests when changing these boundaries; lint and
formatting alone do not verify approval, recovery, or delivery invariants.

## Components

`src/server.mjs` enforces authentication, validation, permission policy, durable approvals,
audit and metrics. `src/operations.mjs` delegates knowledge to the existing CLI and workflows
to a configured upstream API. Its READ `homelab.listServices` operation, exposed
as GET `/homelab/services` and MCP `homelab_list_services`, returns only service
identifiers and restart levels from `policy.services`, labelled as configured
tool coverage. It makes no Docker/broker call and makes no runtime health claim.
Restart authorization and confirmation checks remain authoritative.
See [service discovery and rollout](../hermes/README.md#service-discovery-and-rollout)
for the response and operator deployment steps. The gateway and Hermes rollout
passed on 2026-10-22; see [the deployment record](../../reports/2026-10-22-homelab-service-discovery.md)
for the checks performed and remaining live behavioral acceptance.
`src/project-vault.mjs` adapts completed Mentory records
to the existing router format and maps citations back to original sources; it does not rank
or search documents. `src/homelab-vault.mjs` projects only allowlisted homelab operational
docs and separately labelled historical incidents using the same snapshot/citation support.
Refresh from the repo root with `scripts/build_mentory_knowledge.mjs` or
`scripts/build_homelab_knowledge.mjs`; the latter supports a read-only `--check` for freshness.
See the Hermes guide for commands and snapshot metadata. `src/broker.mjs` is the only component with a Docker socket;
it supports allowlisted inspect/log/restart operations only.
Approved restarts send one Docker write, then inspect container state for up to ten
seconds. Results distinguish healthy, running without a health check, unhealthy/stopped,
starting at the deadline, unavailable verification, and an uncertain restart request.
Verification never retries the write. See [restart verification and rollout](../hermes/README.md#restart-verification-and-rollout)
for the structured response, request budgets and deployment steps.

`src/matrix-approvals.mjs` is the separate trusted approval relay. Completed planning
runs produce a deterministic English notice and complete UTF-8 Markdown attachments
from the gateway-sanitized response, using the existing Matrix account. Delivery
state retains sanitized plan text, media URIs and acknowledged event IDs across
restarts. Ambiguous uploads require review; incomplete delivery preserves a failure
record and a bounded text fallback. See [delivery and recovery](../hermes/README.md#planning-result-delivery)
and [the 2026-10-23 relay deployment record](../../reports/2026-10-23-flowforge-matrix-delivery.md).

Start with `policy.example.json`, an empty workflow allowlist, and explicit service policies.
No runtime, planner, general memory, scheduler or business pipeline is implemented here.
