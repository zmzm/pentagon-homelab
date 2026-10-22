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
to a configured upstream API. `src/project-vault.mjs` adapts completed Mentory records
to the existing router format and maps citations back to original sources; it does not rank
or search documents. `src/homelab-vault.mjs` projects only allowlisted homelab operational
docs and separately labelled historical incidents using the same snapshot/citation support.
Refresh from the repo root with `scripts/build_mentory_knowledge.mjs` or
`scripts/build_homelab_knowledge.mjs`; the latter supports a read-only `--check` for freshness.
See the Hermes guide for commands and snapshot metadata. `src/broker.mjs` is the only component with a Docker socket;
it supports allowlisted inspect/log/restart operations only.

Start with `policy.example.json`, an empty workflow allowlist, and explicit service policies.
No runtime, planner, general memory, scheduler or business pipeline is implemented here.
