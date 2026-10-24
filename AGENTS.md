# Engineering instructions

## Start here

- Read [engineering guidance](docs/engineering.md) for invariants, state/recovery,
  contracts, verification choices, rollout, and known gaps. Inspect the relevant
  implementation and tests before editing; acceptance reports establish only
  what was observed in their deployment.
- [Architecture](ARCHITECTURE.md), [services](SERVICES.md), and
  [operations](OPERATIONS.md) describe the homelab. The
  [Hermes guide](apps/hermes/README.md) is the detailed personal-agent API and
  operating reference; [Compose](apps/hermes/docker-compose.yml) defines deployment.
- Component map: [Hermes](apps/hermes) owns conversation, native memory, skills,
  and conversational schedules; its Python MCP bridge calls the
  [gateway](apps/flowforge-gateway/src/server.mjs), which owns tool contracts,
  policy, approvals, and audit. The [broker](apps/flowforge-gateway/src/broker.mjs)
  alone handles Docker for this stack. The
  [Matrix relay](apps/flowforge-gateway/src/matrix-approvals.mjs) verifies approval
  events and delivers results. The [FlowForge adapter](apps/flowforge/adapter.py)
  delegates planning to the existing runner. Knowledge Router owns retrieval;
  the gateway's `*-vault.mjs` modules select sources and map citations.

## Shared Coding Vault

Locate `zmzm/obsidian-vaults` through the effective `CODING_VAULT_PATH` environment
or `apps/hermes/.env` setting and the Compose vault mount/default; see
[discovery and revision](docs/engineering.md#shared-guidance-and-provenance).
Do not assume a fixed host path or print credentials while inspecting configuration.
The configured path is the `coding` root: read its `AGENTS.md`, `index.md`,
`common/INDEX.md`, `RULES.md`, and `common/engineering/SKILL.md`, then only the
references needed for the task:

| Task | Engineering reference under `common/engineering/references/` |
| --- | --- |
| Approval, execution, delivery state/recovery | `state-and-recovery.md` |
| Retries, timeouts, uncertain effects | `retries-and-idempotency.md` |
| API/configuration or persisted-state changes | `contracts-and-validation.md` |
| Failure handling and diagnostics | `errors-and-observability.md` |
| Structural refactoring | `readability-and-boundaries.md` |
| Checks, rollout, evidence and authorization | `verification-and-change-safety.md` |

Read the actual files; a URL or search excerpt does not load their instructions.
If unavailable, inspect existing behavior/tests, report the missing guidance and
its effect on the task, and do not claim it was loaded. Preserve applicable
nested instructions and unrelated user changes, including in sibling repositories.

## Preserve these invariants

- Keep Docker socket access confined to the broker within this agent stack;
  keep its operations network private and credentials separate. Hermes must
  not receive the approver credential. Model session/request fields are audit
  annotations, not authenticated identity.
- Bind approval to the stored action/arguments and session; consume before
  execution. Preserve durable execution claims. Never automatically replay an
  uncertain write, interrupted planning run, or ambiguous media upload.
- Keep execution, Docker verification, and result delivery separate. Running
  containers do not prove application recovery, external reachability, or backups.
- Keep planning limited to concept/grounded steps, private snapshots/queues,
  and read-only source mounts. Preserve production queues, timers, and native
  Hermes state. Deliver only gateway-sanitized plans, never raw runner files.
- Preserve source allowlists, original citations, historical/source-kind labels,
  snapshot freshness limits, bounded outputs, safe errors, and redaction.
- Diagnosis is procedurally read-only; production still exposes write tools.
  Do not describe model instructions or local locks as stronger enforcement.

## Scope and delivery

Assess API and stored-record compatibility explicitly. Prefer readable conditions
and explicit mutations, following existing Node ESM/Python conventions; separate
behavior-preserving refactors from features where practical.
Run component-appropriate checks from the [verification matrix](docs/engineering.md#verification-matrix)
and report actual passes, failures, skips, and evidence limits. Do not run every
suite for every edit. Separate implementation, testing, deployment, and live
acceptance. Respect the user's existing task authorization: continue routine
authorized work without repeated approval requests; documentation alone does
not authorize deployment, service restarts, paid calls, index rebuilds, or
manufactured Matrix user events/session resets.
