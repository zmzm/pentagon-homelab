# Project engineering guide

This guide describes the implementation at homelab revision `a5a74386f0d65f586d924dde68f413d23e44ba62`
and the documentation-only change introducing this guide. Code, configuration,
and tests establish current behavior; dated acceptance reports establish observations
in a particular deployment. Updating this guide does not deploy any change.

The sections below distinguish **enforced behavior**, **procedural/model instructions**,
**limitations/assumptions**, **recommended development practice**, and **proposals**.
An enforced guarantee is scoped to its implementation and storage assumptions,
not a promise about every crash, host failure, or future model response.

## Shared guidance and provenance

Read the shared [engineering skill](/home/pentagon-admin/Documents/apps/obsidian-vaults/coding/common/engineering/SKILL.md)
from the local checkout. This document records its project-specific application.
Read the actual local skill and relevant references; a link or retrieval snippet
alone does not load their instructions.

The verified checkout configured by `apps/hermes/.env` on this host is:

```text
Repository:        /home/pentagon-admin/Documents/apps/obsidian-vaults
Coding root:       /home/pentagon-admin/Documents/apps/obsidian-vaults/coding
Engineering skill: /home/pentagon-admin/Documents/apps/obsidian-vaults/coding/common/engineering/SKILL.md
References:        /home/pentagon-admin/Documents/apps/obsidian-vaults/coding/common/engineering/references
```

Use these local files directly. Do not fetch, pull, clone, browse GitHub, or use
remote repository tools to load or revalidate guidance that is available locally.
Preserve local vault modifications; do not reset or update the checkout to match
the recorded revision. Local revision/status inspection is sufficient when
provenance matters.

On another machine, locate an existing local checkout through `CODING_VAULT_PATH`
in the environment or private `apps/hermes/.env`, and verify the vault mounts/defaults
in [Compose](../apps/hermes/docker-compose.yml) and [the example](../apps/hermes/.env.example).
Resolve relative defaults from `apps/hermes`. The configured value is the `coding`
root, not the repository root. Do not source arbitrary environment files or print
credentials. If the configured path is unavailable, check other configured local
locations, report missing guidance and its effect, and proceed from existing
code/tests within scope. Do not automatically substitute a remote fetch or claim
that unread guidance was loaded.

Follow the local vault's [AGENTS.md](/home/pentagon-admin/Documents/apps/obsidian-vaults/coding/AGENTS.md),
[index.md](/home/pentagon-admin/Documents/apps/obsidian-vaults/coding/index.md),
[common/INDEX.md](/home/pentagon-admin/Documents/apps/obsidian-vaults/coding/common/INDEX.md),
and [RULES.md](/home/pentagon-admin/Documents/apps/obsidian-vaults/coding/RULES.md)
when reading the engineering skill. Select only references relevant to the decision:

| Decision | Local shared reference |
| --- | --- |
| State transitions, persistence, recovery | [State and recovery](/home/pentagon-admin/Documents/apps/obsidian-vaults/coding/common/engineering/references/state-and-recovery.md) |
| Uncertain effects and retry budgets | [Retries and idempotency](/home/pentagon-admin/Documents/apps/obsidian-vaults/coding/common/engineering/references/retries-and-idempotency.md) |
| APIs, configuration, stored formats | [Contracts and validation](/home/pentagon-admin/Documents/apps/obsidian-vaults/coding/common/engineering/references/contracts-and-validation.md) |
| Errors, diagnostics, health evidence | [Errors and observability](/home/pentagon-admin/Documents/apps/obsidian-vaults/coding/common/engineering/references/errors-and-observability.md) |
| Refactoring and module boundaries | [Readability and boundaries](/home/pentagon-admin/Documents/apps/obsidian-vaults/coding/common/engineering/references/readability-and-boundaries.md) |
| Verification and authorized rollout | [Verification and change safety](/home/pentagon-admin/Documents/apps/obsidian-vaults/coding/common/engineering/references/verification-and-change-safety.md) |

Revision used to establish this guide: **`0f3abe5374c5ad2ec4bd11fe4788819eb0c0e55d`**.
The initial verification on 2026-10-24 confirmed the skill was integrated into the
remote default branch `main`, with the feature branch at the same revision; no
feature-branch merge prerequisite remained. This is recorded provenance, not an
instruction to repeat a remote check. The loaded engineering/navigation/rules files
matched that commit, and unrelated local changes were preserved. For future work,
read the current local files and disclose relevant differences from this baseline.

## Component responsibilities and sources of truth

| Component | Responsibility and implementation | Inspect with it |
| --- | --- | --- |
| Hermes | Conversation, native memory/session search, curated native skills, new conversational schedules. [Configuration](../apps/hermes/config.yaml), [SOUL](../apps/hermes/SOUL.md), [diagnosis skill](../apps/hermes/skills/homelab-service-diagnosis/SKILL.md), [selection plugin](../apps/hermes/plugins/homelab-skill-tools/__init__.py) | [Runtime/API guide](../apps/hermes/README.md), [bridge tests](../apps/hermes/test_gateway_mcp.py) and registration scripts below |
| MCP bridge | Nine Python stdio tools forwarding HTTP; no independent permission authority. [gateway_mcp.py](../apps/hermes/gateway_mcp.py) | Bridge tests; effective installed CLI/Matrix/cron selection |
| Personal gateway | Tool contracts, input validation, policy, persisted approvals, write-start/final audit, metrics. [server.mjs](../apps/flowforge-gateway/src/server.mjs), [operations.mjs](../apps/flowforge-gateway/src/operations.mjs), [common.mjs](../apps/flowforge-gateway/src/common.mjs) | [Policy actually mounted by Compose](../apps/flowforge-gateway/policy.example.json), [gateway tests](../apps/flowforge-gateway/test/gateway.test.mjs) |
| Docker broker | Narrow authenticated inspect/log/restart integration. [broker.mjs](../apps/flowforge-gateway/src/broker.mjs), [restart.mjs](../apps/flowforge-gateway/src/restart.mjs) | [Restart tests](../apps/flowforge-gateway/test/restart.test.mjs) and gateway broker fixtures |
| FlowForge adapter | Planning-only wrapper around existing `pipeline_runner.run_selected_task`; source snapshots, run records, private task queue. [adapter.py](../apps/flowforge/adapter.py) | [Adapter guide](../apps/flowforge/README.md), [tests](../apps/flowforge/test_adapter.py), mounted external runner/steps/agent definitions |
| Matrix relay | Trusted approval-event filtering, stored-action execution request, polling and sanitized result delivery. [matrix-approvals.mjs](../apps/flowforge-gateway/src/matrix-approvals.mjs) | [Approval tests](../apps/flowforge-gateway/test/matrix-approvals.test.mjs), [delivery tests](../apps/flowforge-gateway/test/workflow-delivery.test.mjs) |
| Knowledge Router / projections | Existing external CLI owns ranking/retrieval. [project-vault.mjs](../apps/flowforge-gateway/src/project-vault.mjs) and [homelab-vault.mjs](../apps/flowforge-gateway/src/homelab-vault.mjs) select sources, publish snapshots, translate citations | [Project tests](../apps/flowforge-gateway/test/project-vault.test.mjs), [homelab tests](../apps/flowforge-gateway/test/homelab-vault.test.mjs), external CLI selected by `KNOWLEDGE_CLI` |

[Architecture](../ARCHITECTURE.md), [services](../SERVICES.md),
[operations](../OPERATIONS.md), and [recovery](../RECOVERY_CHECKLIST.md) cover
the wider homelab. Existing production FlowForge timers, monitoring, backup
jobs, and other Compose projects remain independent. Do not add a second
planner, scheduler, retrieval engine, or general memory system to the gateway.

## Trust and authorization

**Enforced by this stack's Compose and code:** no published host ports; Hermes
joins agent/egress networks, gateway joins agent/operations/upstream, broker
joins operations only, adapter joins upstream/egress, relay joins agent/egress.
Internal networks isolate broker and adapter from Hermes; gateway has no
configured direct internet-egress network. This is not a host-compromise or
compromised-neighbor security guarantee.

Only the broker in this personal-agent stack mounts `/var/run/docker.sock`.
Other homelab management services have their own Docker privileges; this rule
does not describe every service on the host. A `:ro` socket mount still permits
Docker writes. The protection is the narrow handler, service allowlist, bearer
credential, and isolated operations network. The broker rechecks policy and
rejects DENY, but does **not** verify a CONFIRM approval or write audit itself.
It trusts the gateway to do that. Keep untrusted workloads off operations and
keep `BROKER_TOKEN` exclusive to gateway/broker. Host/Docker administrators
remain trusted; no arbitrary Docker URL, create, or exec endpoint is exposed.

Hermes receives the gateway credential, never `APPROVER_TOKEN`. The relay has
the approver and Matrix credentials, without broker/FlowForge credentials.
Compose requests four distinct credentials; code explicitly checks only the
gateway/approver pair for inequality. Operators must preserve all four-way
separation. The approver API trusts its credential holder: it does not itself
authenticate Matrix events. The relay verifies allowed sender, exact room,
freshness, pending prompt, reaction target or strict text command, and ignores
edits/redactions and limited-sync gaps. First valid local decision wins.
Keep the bot excluded from `MATRIX_ALLOWED_USERS`; filtering relies on that
configuration, not a separate bot-identity test. Unencrypted rooms are required;
the relay checks room state before sends/uploads and refuses encrypted rooms.

`session_id`/`user_request` become percent-encoded audit headers. They are
model-supplied annotations, not user authentication. Approval execution requires
an unexpired APPROVED record matching tool, canonical arguments, and stored
session. The approver `/execute` route uses the stored action directly.

**Procedural/model instructions:** SOUL and the diagnosis skill require read-only
diagnosis, an actual user choice for ambiguous targets, no approval creation,
and bounded diagnostic reads. Write tools remain in the production tool surface;
the validation harness's read-only HTTP guard is not a production per-request
restriction. Preserve this distinction when reporting security or model behavior.
Service discovery reports configured policy coverage, never running health.

## State transitions and recovery

### Approval and execution

The gateway stores one JSON record per UUID in `/state/approvals`; it appends
redacted JSONL audit entries. [Server](../apps/flowforge-gateway/src/server.mjs)
saves via flushed temporary file, rename, and parent-directory fsync. Audit
entries use flushed appends. This orders local evidence around effects; it is
not a transaction with Docker, Matrix, or FlowForge, and does not establish
durability beyond the host filesystem/storage and preserved volume.

| Stored state / transition | Owner and meaning | Recovery constraint |
| --- | --- | --- |
| New → `PENDING` | Gateway persists exact request; ten-minute expiry; no execution | Pending list omits expired records; expiry does not rewrite gateway status |
| `PENDING` → `APPROVED` / `REJECTED` | Approver-authenticated decision; audit before decision save | Relay persists verified event before submitting decision; can reconcile gateway state |
| `APPROVED` → `CONSUMED` | Gateway synchronously saves claim before awaiting external effect | A second invocation cannot consume it in the same gateway process; do not reset it |
| `CONSUMED` → `DONE` | Execution returned and final audit/outcome saved | Restart DONE means acknowledgment; workflow DONE here means submission returned, not planning completed |
| `CONSUMED` → `UNCERTAIN` | Restart acknowledgment/broker response lost | Safe inspection and operator review; no automatic write replay |
| `CONSUMED` → `FAILED` | Caught execution/processing failure when failure recording succeeds | Failure may follow an external effect; it is not proof nothing happened |
| Left `CONSUMED` after interruption | No automatic gateway startup reconciliation | Relay reports uncertainty; operator owns investigation |

The audit start must succeed before dispatch, including AUTO_SAFE operations.
Failure after consuming but before dispatch can abandon an action safely;
failure after dispatch but before outcome persistence can lose confirmation.
Neither window authorizes replay. Result/audit persistence failures may leave
CONSUMED or a failure response even after the remote operation succeeded.
AUTO_SAFE operations have no approval execution claim; a fresh request can
execute again. The mounted policy currently uses CONFIRM for task-analysis
and all permitted restarts, with Homepage DENY.

The relay persists prompt preparation, prompt event ID/controls, decision,
sync cursor, and `executionAttempted` before the execution HTTP request. A crash
after that claim but before dispatch can leave gateway APPROVED with no effect;
the relay chooses no automatic replay and reports uncertainty. A lost run
submission response can leave a real adapter run without a run ID in gateway
outcome; there is no submission idempotency key or automatic cross-service
reconciliation. Check retained adapter/audit evidence before any new request.
Gateway expiry is checked again on execution. Relay `EXPIRED` is a reporting
value, not a persisted gateway approval state.

### Planning runs

**Enforced:** the adapter validates workflow/project/fields/task hash and paths,
copies tracked working-tree files into a private project, copies approved task
bytes/context, and writes a private concept/grounded queue. It excludes project
runtime configuration/plugins/execution agents and selected secret file patterns,
uses read-only source mounts, and applies scoped OpenCode permissions. This is
not general secret detection or an atomic repository snapshot. The hash binds
the task only; other source files can change while copied. Large files above
16 MiB are omitted with a manifest; total copied sources are capped at 128 MiB.
Output API files are capped at 40,000 bytes each. Inspect effective OpenCode
permissions when upgrading; parsing config alone does not prove tool access.

| Run state | Persistence/effect ordering | Recovery owner |
| --- | --- | --- |
| Preparation (no status yet) | Private folder/snapshot before accepted run record | Failed preparation removes folder if no status exists; crashes can leave orphan folders |
| `RUNNING` | Fsynced `status.json` before spawning worker; response includes UUID | Adapter allows one active recorded run; no waiting queue |
| `DONE` / `FAILED` | Worker saves terminal status and available outputs after runner returns | Read by UUID; no automatic rerun |
| Stale `RUNNING` at adapter startup | Rewritten `FAILED` / `INTERRUPTED_REVIEW_REQUIRED` | Operator reviews partial artifacts; no replay |
| Child exits while still `RUNNING` | Reaper writes `FAILED` / `RUNNER_EXITED_REVIEW_REQUIRED` | Operator reviews; no replay |

Each planning step has a configured 900-second timeout. DONE follows runner
`result.ok`; it does not require both plan files to exist. Delivery separately
detects missing plans. A process-local Python lock serializes submissions;
the existing runner locks a private run directory. These do not coordinate
multiple adapter instances or fence surviving workers. Startup recovery assumes
old workers stopped with the container. Run one adapter, one gateway, and one
relay. Gateway synchronous claim-before-await and relay sequential ticks/file
state are not distributed locks. There is no universal exactly-once guarantee.

### Result delivery

Execution success, verification, and delivery have different evidence. Gateway
workflow submission stores a run ID; the relay polls that specific run through
the authenticated gateway. It freezes **gateway-redacted** plan text and message
bodies in its own persisted state before any completion delivery. It has no
raw output filesystem mount and makes no summarizing model call.

| Delivery state/field | Transition and evidence | Recovery |
| --- | --- | --- |
| `workflowPending` | Accepted run-start notice sets polling flag | Run lookup failures retry independently without re-execution |
| `workflowDelivery.status: pending` | Terminal run snapshot saved before completion notice | Reuse frozen text and transaction IDs |
| File `pending` → `uploading` | Attempt claim saved before media POST | Interrupted claim becomes `uncertain` |
| File `uploaded` | Valid `mxc://` URI saved after upload | Reuse URI; send file event without reupload |
| File `failed` / `uncertain` | Explicit rejection / ambiguous response | No automatic upload replay, except bounded 429 retries |
| File `eventId` | Homeserver acknowledgment saved for file event | Confirmed file not resent; unconfirmed send retries same transaction/content |
| Delivery `delivered` | Both required file events acknowledged; FAILED runs require only short failure notice | Clear polling; eligible for completed-prompt pruning |
| Delivery `failed` | Missing or unacknowledged attachment; bounded fallback | Retain full available sanitized text/failure; retry only eligible work |

Media POST has no transaction ID. Timeout, HTTP 408/5xx, invalid URI, or crash
before URI persistence stops that upload for review. Only explicit 429 rejection
retries, at most three attempts, minimum 30-second delay with bounded server retry
timing. The fallback retains at most 3,000 UTF-8 bytes per undelivered plan with
truncation markers; it does not turn failed attachments into successful delivery.
Failed delivery records are excluded from normal pruning (up to 200 ordinary
completed prompts are retained). Stable Matrix message transaction IDs rely on
the existing account/token and homeserver deduplication semantics; preserve them.
An acknowledged event proves homeserver acceptance, not that the user read it.

Operator recovery: stop the relay and back up state before manual edits; retain
approval decisions and claims. Reconcile uncertain uploads against Matrix and
recover the accepted URI when possible. If unresolved, preserve uncertainty and
review retained sanitized text. Do not clear claims blindly, attach raw adapter
files, or rerun paid planning to repair delivery. See the existing
[delivery procedure](../apps/hermes/README.md#planning-result-delivery).

## Contracts and compatibility

Externally consumed contracts include the [HTTP/approver API](../apps/hermes/README.md#stable-tool-api),
the nine [MCP schemas](../apps/hermes/gateway_mcp.py), policy/configuration fields,
broker POST `/execute`, adapter GET `/tasks`, POST `/run`, GET `/runs/:id`,
Matrix commands/reactions/file events, operator CLI, and Knowledge Router CLI
arguments/results/citation metadata. Most success responses wrap `data`;
APPROVAL_REQUIRED is a failure-shaped HTTP 200 with ID/expiry. Avoid changing
response nesting, enum meanings, units, or tool defaults without checking consumers.

| Stored format | Current reader behavior and limits |
| --- | --- |
| Gateway `approvals/<uuid>.json`, `audit.jsonl` | JSON approvals have no schema version/full load validation. Read/parse errors become APPROVAL_NOT_FOUND; a malformed file in list enumeration can fail the list. Unknown statuses cannot satisfy APPROVED but can be reported verbatim. Audit is append-only evidence, not replay input. |
| Relay `matrix-approvals.json` | Missing file starts empty; invalid JSON aborts startup. Constructor initializes missing `prompts`; records have no complete schema/version validation or migration. Unknown upload states are not automatically retryable. |
| Adapter `<uuid>/status.json`, private queue/steps/output | JSON without version/full record validation; startup assumes valid `status`. Corrupt records can prevent startup or submission. Existing unknown states are not reconciled; relay accepts only RUNNING/DONE/FAILED. |
| Knowledge `current.json`, `snapshots/<id>/manifest.json`, projected files, per-snapshot caches | Pointer ID, path, project and manifest version 1 checked; homelab timestamps checked. Wrong/missing/unsupported snapshots fail as KNOWLEDGE_PROJECT_NOT_READY. Validation is partial, not a full manifest/document integrity audit. Stale snapshots stay searchable with metadata. |
| Hermes native home | Memory, skills, sessions, cron and native logs belong to installed Hermes; preserve mount and native formats. Do not migrate by hand as a gateway change. |

**Current validation:** unknown command fields, bounded payloads, identifiers,
policy levels, task hash, and selected upstream state fields are checked at
their boundaries. `object()` rejects extra keys but does not itself require
all fields; callers supply further checks. Upstream JSON decoding is not a
comprehensive response schema. Python annotations and MCP schemas do not replace
gateway/adapter runtime checks. State and snapshot publication differ: gateway,
relay, and adapter flush/fsync their local records; knowledge publication uses
rename without explicit fsync and claims atomic publication, not equivalent
power-loss durability.

**Required practice for changes:** assess old records, malformed/unknown records,
all producers/consumers, mixed-version rollout and rollback before altering
states, field meaning, response shapes or stored files. Define missing/null/unknown
behavior. If migration is needed, back up state, specify versioned reader/writer
order, migrate with processing quiesced where necessary, verify readback, and
describe rollback to a reader that understands the retained format. Never
rollback by deleting claims or restoring old state that makes completed actions
appear executable. Full schemas/quarantine/migrations are proposals below,
not capabilities to assume today.

## Errors, timeouts, and evidence

Preserve safe categories such as INVALID_INPUT, UNAUTHORIZED, POLICY_DENIED,
APPROVAL_REQUIRED, INVALID_APPROVAL, UPSTREAM_FAILED/UNAVAILABLE,
RESTART_UNCERTAIN, INTERRUPTED_REVIEW_REQUIRED and MATRIX_UPLOAD_UNCONFIRMED.
Unknown failures are translated to bounded generic codes. Do not expose raw
upstream errors, tracebacks, environment/configuration, or credentials to Matrix.
Gateway redacts sensitive field names, known credential values and common secret
patterns; broker inspection returns selected state only, and logs redact known
container-env secrets. Arbitrary unlabeled secrets can escape pattern redaction:
applications must avoid emitting them. Preserve relay attachment name allowlisting
and sanitized-response-only boundary.

| Layer / operation | Current budget and retry ownership |
| --- | --- |
| Broker restart | One Docker POST, absolute 15 seconds including body; no retry |
| Restart verification | Separate 10 seconds; reads capped at 2 seconds/remaining time, 500 ms between starting observations; only `starting` polls again |
| Gateway upstream / retrieval | 30-second fetch or CLI deadline; no built-in write retry; 64 KiB input / 128 KiB result bounds |
| Relay client / tick | 35-second requests; sequential tick then 3-second delay; per-operation failures isolated and retried as state allows |
| MCP / Hermes | Bridge urllib timeout 35 seconds, configured MCP budget 40 seconds; urllib timeout is not the broker's absolute wall-clock timer |
| FlowForge | 900 seconds per planning step; HTTP submission/status separate from long model execution |

The intended restart nesting is 15 + 10 < 30 < 35 < 40 seconds, with response
headroom. Gateway HTTP `requestTimeout=35000`/`headersTimeout=10000` and adapter
server timeout are not proof of a universal handler/execution deadline. Preserve
bounded reads and budget headroom when changing work inside a request.
The relay owns run polling and delivery retries. There is no total elapsed/attempt
limit for workflow polling or unconfirmed message sends, and no general jittered
backoff; do not document one. Hermes model API retry configuration is separate
from effect retry authorization; SOUL prohibits automatic uncertain write retries.

Docker acknowledgment means the restart endpoint accepted/completed its request.
Verification separately reports `healthy`, `running_no_healthcheck`, `unhealthy`,
`stopped`, `starting_timeout`, `unavailable`, or `not_attempted`. Even DONE with
`success:true` can have unhealthy/unavailable verification. No restart path probes
application recovery, external reachability or backup execution. A successful
backup requires backup-job evidence; restored-application tests establish their
own limited recovery evidence. Gateway `/health` is process liveness, not dependency
readiness. Compose waiting on it is only that readiness criterion; other custom
services have no Compose healthcheck.

Keep diagnostic evidence in private native tool/session traces, redacted gateway
audit and relay state/logs. Gateway metrics reset at process restart. Hermes
Matrix display settings suppress tool progress/intermediate commentary while
retaining native logs; presentation is not a permission boundary. User replies
should explain observed facts, documentation, hypotheses and material limits in
plain English without dumping internal traces. No unified exporter, automatic
state retention policy, or backup-success tool API exists here.

## Code organization and runtime instructions

**Recommended practice:** follow Node 24+ standard-library ESM (`.mjs`, `node:test`)
and Python stdlib/unittest conventions. MCP/Pydantic come from the installed
Hermes environment. The custom [gateway Dockerfile](../apps/flowforge-gateway/Dockerfile)
uses Node Alpine; the [adapter Dockerfile](../apps/flowforge/Dockerfile) adds
Python/git on Node Debian. Keep readable conditions, explicit state mutations,
and effect ordering visible. Separate transport parsing, domain decisions and
persistence when their coupling makes maintenance difficult; small functions
can provide that boundary. No arbitrary file-length rule, mandatory framework,
universal class layer, or JavaScript-to-TypeScript rewrite is required. Preserve
behavior when refactoring and separate structural work from features where practical.

[Root AGENTS](../AGENTS.md) and this guide instruct development agents; they are
not mounted as the running Hermes identity. Compose mounts `config.yaml`,
`SOUL.md`, `gateway_mcp.py`, curated `skills`, and the selection plugin. Hermes
native state lives in `data/hermes`. Keep the engineering guide out of SOUL and
runtime skills; those files contain scoped conversational procedures. The plugin
uses installed Hermes toolset internals, so check effective schemas after upgrades
rather than trusting upstream examples or direct MCP registration alone.

After tool/schema/include-list changes, verify the native subprocess environment
and all CLI/Matrix/cron selections. Continuing conversations may retain saved
system prompts and previously loaded skills despite recreation. Validate revised
behavior in fresh sessions. For Matrix, the user sends standalone `!new`, chooses
**Approve Once** if prompted, and waits for confirmation. Preserve that guard;
never manufacture the event, approval, or conversation reset on their behalf.

Knowledge snapshots require explicit operator refresh after allowlisted source
changes, preferably after commit. The allowlist is `HOMELAB_DOCUMENTS` plus direct
`incidents/*.md` in [homelab-vault.mjs](../apps/flowforge-gateway/src/homelab-vault.mjs);
it does not follow links. **Neither AGENTS.md nor this guide is currently included.**
Adding them would be a separate retrieval-scope decision. Homelab checks compare
source/version and a seven-day freshness threshold; search alone reports
`sourceChanges: unknown` and cannot inspect the live repository. Mentory selects
completed-task Markdown/README/SUMMARY, not arbitrary source code or upcoming tasks.
Keep original citations/source kinds; historical incidents and planning documents
do not establish present implementation. Snapshot refresh creates new state/index
inputs and is separate from a documentation edit; use the existing
[operator refresh commands](../apps/hermes/README.md#homelab-documentation) only
within authorization. Documentation-only refresh needs no service restart.

## Verification matrix

Select checks for the affected boundary and risk. Read commands before running;
unit validation needs no live service restart or paid model call. Node 24+,
Python 3, Git, Docker/Compose and external checkout dependencies apply only to
the rows using them. Report passed/failed/skipped/unverified with actual scope.

| Check / working directory | Existing command | Prerequisites and evidence limits |
| --- | --- | --- |
| Gateway/broker/approval/restart/delivery; `apps/flowforge-gateway` | `npm test` | Node 24+, local TCP/Unix fixture sockets and temp files; no npm install needed. Fake Docker/Matrix plus real local HTTP boundaries prove modeled behavior, not production effects. |
| Focus one gateway area; same directory | `node --test test/restart.test.mjs` (or `gateway.test.mjs`, `matrix-approvals.test.mjs`, `workflow-delivery.test.mjs` under `test/`) | Include related integration tests when a shared state/response contract changes. |
| FlowForge adapter; repository root | `python3 -m unittest discover -s apps/flowforge -p 'test_*.py'` | Python/Git/temp writable tree. Real-runner test skips if sibling `apps/flow-forge-tui/pipeline_runner.py` is absent; its model process boundary is mocked. Does not exercise real OpenCode permissions or GLM. |
| MCP bridge; root | `python3 -m unittest discover -s apps/hermes -p 'test_*.py'` | MCP SDK + Pydantic in chosen Python; mocked HTTP. Missing imports are an unavailable environment, not a passing skip. Can use installed image in a disposable no-network container and read-only test mount; the current fixture has an installed-SDK attribute mismatch recorded below. |
| Skill behavior checker/HTTP guard regressions; root | `python3 -m unittest discover -s scripts -p 'test_verify_hermes_skills.py'` | Python stdlib; checks trace interpretation including deferred calls, ambiguity and validation guard, not actual model behavior. |
| Offline installed-image skill/native registration; root | `python3 scripts/verify_hermes_skills.py` | Docker access and existing `personal-agent-hermes-1` image/container/skill tree. Disposable network-disabled tmpfs home, fixture credentials; checks native loading, exact skill bytes, CLI/Matrix/cron effective tool inventory and isolation hashes. Writes ignored evidence; no Matrix/model requests. |
| Deployed native registration; `apps/hermes` | `docker compose exec -T hermes python - < ../../scripts/verify_hermes_tool_registration.py` | Installed Hermes/MCP/plugin/mounts; starts bridge and reads skills, may update native caches. No personal-tool/model calls. Prefer offline row for proposed changes. |
| Read-only deployed MCP smoke; `apps/hermes` | `docker compose exec -T hermes python - < ../../scripts/verify_hermes_mcp.py` | Running gateway/broker and allowlisted Vaultwarden; real handshake/schema, policy discovery and inspection. Appends gateway audit; no write approval, restart, Matrix send or model call. |
| Native planning preflight; `apps/hermes` | `docker compose exec -T flowforge-api python3 - < ../../scripts/verify_flowforge_preflight.py` | Installed runner/OpenCode/source mounts; creates retained private preflight snapshot/state, exercises real allowed/denied reads/writes/shell, no model. Schedule away from active planning; not a pure read-only check or ordinary unit prerequisite. |
| Live skill behavior; root, separate authorization | `python3 scripts/verify_hermes_skills.py --live` | Existing GLM/gateway credentials, model cost and diagnostic-data egress. Isolated CLI sessions with validation-only read guard; manual answer/evidence review still required. Does not prove end-to-end Matrix behavior. |
| Compose; `apps/hermes` | `docker compose config --quiet` | Existing complete private `.env`/environment; validates interpolation/shape, not images, reachability, socket access, effective permissions or deployment. Do not print expanded secrets. |
| Projection/citation tests; `apps/flowforge-gateway` | `node --test test/homelab-vault.test.mjs test/project-vault.test.mjs` | Node/Git/temp state. Real retrieval cases need built external Knowledge Router at `KNOWLEDGE_CLI` or sibling default; skip honestly when absent. Fixture publication alone does not prove retrieval. |
| Existing homelab snapshot; root | `node scripts/build_homelab_knowledge.mjs --project "$PWD" --output "$PWD/data/knowledge-homelab" --check` | Read-only comparison, existing projection; exits 1 when missing/invalid/stale/source changed. No rebuild. After a commit, changed source revision can require a later authorized refresh even if selected document bytes did not change. |

For monitoring, backup/recovery, or Ansible changes, select their existing
`scripts/test_*.py` and [Ansible checks](../ansible/README.md) according to scope;
do not use restore/live application scripts as universal unit checks. Neither
real Matrix approval events, a production restart, paid workflow, nor native
memory acceptance is necessary to validate an ordinary code/documentation edit.

### Validation of this documentation change (2026-10-24)

No pre-existing AGENTS.md was found in this repository or its inspected ancestor
directories. The shared vault's applicable navigation/rules were read and retained.
The new files were checked against the implementation/tests linked above.

- Node 24.14.1 `npm test`: **81 passed, 0 skipped**, including actual external
  Knowledge Router retrieval and fake-socket restart deadlines. The initial
  restricted-environment run failed at file level without useful diagnostics;
  the rerun with local fixture socket access passed.
- Adapter unittest: **7 passed**, including the existing runner with mocked model
  boundary. Skill-checker unittest: **8 passed**.
- Bridge unittest in a disposable no-network installed-image container:
  **2 passed, 1 error**. The native `Tool` exposes `input_schema`, while the fixture
  accesses `inputSchema`. Host Python lacks MCP/Pydantic; no dependencies installed.
- Offline skill harness: **passed**, including installed native registration,
  exact skill loading, all platform selections and production isolation checks.
  Read-only deployed MCP handshake/discovery/Vaultwarden inspection: **passed**.
- Compose quiet validation: **passed**. Read-only homelab snapshot check before
  committing: **ready, unchanged, not stale** at the implementation revision above.
  Committing changes Git revision metadata, which requires a later operator
  refresh for `--check` to report current again; no production snapshot/index rebuilt.
- Relative file/anchor links, command paths and whitespace were checked locally.
  Paid/live skill behavior, native state-producing FlowForge preflight, Matrix
  approval/attachment sends, service restarts/deployment and live acceptance were
  **not run**. Prior reports were not substituted for these checks.

## Component-specific rollout

These are operator instructions **when deployment is authorized**, not actions
implied by writing documentation. Determine affected services from Compose build
contexts, mounts, environment and consumers. Check pending/approved/consumed
approvals, relay `workflowPending`/delivery claims, adapter RUNNING records, and
Hermes conversations/cron work before interrupting processing. Use protected
read-only inspection; do not manufacture requests to discover active work.
Let work finish or record an explicit recovery plan before interruption.

Preserve `data/hermes`, `data/flowforge-gateway`, `data/matrix-approvals`,
`data/flowforge-api`, knowledge projections, source mounts and private `.env`
credentials/Matrix account. Preserve UID/GID ownership and private modes. Do not
use `down -v`, delete claims, rotate tokens casually, or restore stale state to
force retries. Back up state before schema migration/manual recovery.

From `apps/hermes`, first run `docker compose config --quiet`. For image changes
use `docker compose build SERVICE`, then `docker compose up -d --no-deps SERVICE`
for only the required service(s). Bind-mounted/config-only changes may require
`--force-recreate` to reload; no image rebuild is needed merely for a mount edit.

| Change | Affected services / verification |
| --- | --- |
| Gateway contracts/executor | Rebuild/recreate `flowforge-gateway`; wait for health, inspect safe logs and relevant read path. Reload Hermes if MCP contract/selection changes too. |
| Broker/restart logic | Rebuild/recreate `homelab-broker`; include gateway/relay only if their consumed contracts changed. Verify safe inspection; no test restart by default. |
| Relay approval/delivery | Rebuild/recreate `matrix-approvals`; preserve claims/token/state; inspect sanitized logs and retained progress. No planner rebuild/rerun needed for delivery repair. |
| Adapter snapshot/runner wrapper | Rebuild/recreate `flowforge-api` after active planning is settled. Native preflight is a separate state-producing check; no paid planning without its own authorization. External mounted runner/steps changes require compatibility review too. |
| Hermes config/SOUL/skill/plugin/bridge | Recreate only `hermes` as needed; use `--force-recreate` for reload when Compose otherwise sees no change. Verify installed registration/MCP, then fresh user-controlled session for behavior. |
| Policy or shared contract | Gateway and broker both load policy at startup; recreate both for policy changes, plus consumers actually affected. Keep single-instance topology. |
| Allowlisted documentation | Authorized snapshot refresh/check after commit; no service restart. This guide/AGENTS are outside the current allowlist. |

`docker compose ps` and bounded `docker compose logs --tail 50 SERVICE` help
review readiness/failures, with sensitive evidence kept private. `--wait` only
checks configured health/running criteria; the gateway health endpoint alone
does not establish dependency readiness. Read-only registration/smoke checks
verify relevant integration without approving a mutation. Record implementation,
test evidence, deployed version, and live acceptance separately; a successful
Compose invocation does not establish all four.

## Current gaps and follow-up decisions

These findings were not repaired by this documentation change:

- The bridge fixture assumes the MCP SDK's Python `Tool.inputSchema` attribute;
  installed-image execution raises an attribute error suggesting `input_schema`.
  Wire-level registration/smoke checks pass. Decide how to make fixture inspection
  support the SDK versions already supported by the bridge; this is a test
  compatibility gap, not evidence that wire-level tool discovery failed.
- The adapter guide says selection preserves the month gate; GET `/tasks` uses
  it for discovery, but POST `/run` accepts any matching task ID/hash without
  requiring `todo` or current-month eligibility. Decide whether explicit selection
  should retain that behavior or add validation as a contract change.
- Snapshot isolation protects the source repository/queue from planner writes;
  copying a changing working tree is not a coherent Git-revision snapshot. Only
  task bytes are hash-bound. Read-only private source modes are defense in depth
  for the owner UID, while output restrictions depend on effective OpenCode rules.
- DONE run status does not validate the presence of both required plans. The
  relay reports missing outputs as delivery failure; strengthening completion
  validation would change outcome semantics.
- Stored records lack comprehensive versioned schemas, quarantine and migrations.
  Full upstream response validation is also incomplete. Unknown/corrupt record
  behavior above must not be described as universal graceful recovery.
- Consumed/locally claimed execution can be abandoned or uncertain after a crash;
  FlowForge submission lacks idempotent lookup across a lost response. No automatic
  reconciliation service or multi-instance coordination exists.
- Polling/message-send retries have no total budget; failed delivery records and
  immutable snapshots have no automatic retention bound. Operators own disk-use
  and stuck-work review.
- Read-only diagnosis is procedural, four-way token inequality is operational,
  and bot exclusion depends on the allowed-user configuration. Hard request-scoped
  capabilities or additional startup validation would be separate improvements.
- Existing guides contain dated deployed/tested statements (including discovery
  acceptance and restart rollout language). Interpret them with their dates and
  reports, not as evidence that the current checkout is deployed or every live
  path was accepted. Installed skill loading proves neither model selection nor
  response quality. The new engineering files are not automatically retrieved by
  Hermes, because the projection does not follow links or include them.

**Proposed, not implemented:** versioned state readers/migrations and corruption
isolation; durable cross-service submission identity/reconciliation; bounded
delivery polling/send retry policy and retention; enforced diagnostic capabilities;
stronger task/plan validation; coherent source snapshots; storage-coordinated
claims before supporting multiple instances. Evaluate these as scoped changes
with the shared engineering references, compatibility/recovery decisions and
failure-boundary tests. None is a prerequisite to an unrelated routine edit.
