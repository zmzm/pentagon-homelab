# FlowForge gateway

Portable REST boundary for Knowledge Router, existing FlowForge workflows and constrained
Docker operations. Uses Node.js 24+ standard library only. Hermes connects through the
thin MCP adapter in `../hermes/gateway_mcp.py`; other runtimes can use the same HTTP API.

See [deployment, API, policy and acceptance documentation](../hermes/README.md).

```bash
npm test
```

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

Start with `policy.example.json`, an empty workflow allowlist, and explicit service policies.
No runtime, planner, general memory, scheduler or business pipeline is implemented here.
