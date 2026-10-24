# Engineering instructions

## Start here

- Select only the guide sections relevant to the task using the table below;
  do not load all of `docs/engineering.md` by default. For a small scoped edit,
  start with the component map, the invariants here, and relevant code/tests.
  Acceptance reports establish only what was observed in their deployment.
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

| Task | Guide section |
| --- | --- |
| Approvals or authorization | [Trust and authorization](docs/engineering.md#trust-and-authorization) |
| State transitions or recovery | [State transitions and recovery](docs/engineering.md#state-transitions-and-recovery) |
| API or persisted-state compatibility | [Contracts and compatibility](docs/engineering.md#contracts-and-compatibility) |
| Restart verification | [Restart verification](docs/engineering.md#restart-verification) |
| Workflow result delivery | [Result delivery](docs/engineering.md#result-delivery) |
| Deployment or rollout | [Component-specific rollout](docs/engineering.md#component-specific-rollout) |

## Shared Coding Vault

When shared guidance is needed, use the single
[coding-root discovery procedure](docs/engineering.md#shared-guidance-and-provenance)
and retain the resolved root for the task. All **Vault paths** below are relative
to that external coding root, not this repository. Read its applicable `AGENTS.md`
and `common/engineering/SKILL.md`, then only the references relevant to the task;
use its indexes for navigation when needed. Read actual local files, not just
links or search excerpts. No remote fetch is needed for locally available guidance.

| Task | Vault path (relative to resolved coding root) |
| --- | --- |
| Approval, execution, delivery state/recovery | `common/engineering/references/state-and-recovery.md` |
| Retries, timeouts, uncertain effects | `common/engineering/references/retries-and-idempotency.md` |
| API/configuration or persisted-state changes | `common/engineering/references/contracts-and-validation.md` |
| Failure handling and diagnostics | `common/engineering/references/errors-and-observability.md` |
| Structural refactoring | `common/engineering/references/readability-and-boundaries.md` |
| Checks, rollout, evidence and authorization | `common/engineering/references/verification-and-change-safety.md` |

Keep reusable principles in the vault; link the relevant reference instead of
copying or paraphrasing its sections into repository instructions. Retain local
decisions, constraints, evidence, or explicit exceptions. If guidance is missing,
report the limitation and inspect existing behavior/tests without claiming it
was loaded. Preserve applicable nested instructions and unrelated user changes.

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

For shared engineering decisions, use the relevant vault reference above. For
homelab API/state changes, identify affected consumers and retained records in
the compatibility assessment. Use the
[verification matrix](docs/engineering.md#verification-matrix) for component checks
and their evidence limits; unit checks do not require live service restarts or
paid calls. Report actual check scope and distinguish implementation, testing,
deployment and live acceptance. Continue work within existing task authorization
without repeated permission requests. Documentation alone does not authorize
service deployment/restarts, paid calls, index rebuilds, or Matrix user events
and session resets.
