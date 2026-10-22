# Hermes personal runtime PoC

Hermes owns Matrix conversation, sessions, lightweight memory and new conversational
schedules. The gateway owns the stable tool API, permission policy and audit. Knowledge
Router owns retrieval; FlowForge owns planning/workflows. Production FlowForge timers,
monitoring and existing application services remain independent.

## Status

| Capability | Implementation and verification |
| --- | --- |
| Matrix + GLM | Running; a real authorized Matrix request inspected Vaultwarden, read logs and returned an answer |
| Personal MCP tools | Hermes native registration and Matrix filtering tested; read-only Vaultwarden tool chain tested |
| Permissions | READ/AUTO_SAFE/CONFIRM/DENY; exact-action, durable single-use approvals; no model approver credential |
| Matrix approvals | Separate trusted listener posts exact actions and accepts commands or seeded reactions only from allowed Matrix users in the configured room; security tests pass |
| Knowledge Router | Existing router searches coding guidance and a cited snapshot of completed Mentory task records/history; native knowledge → approved FlowForge → Matrix acceptance passed |
| FlowForge | Planning-only API around existing runner, task hashes and read-only source snapshot; real GLM run saved both plans in 633 seconds; all four sanitized result chunks verified in Matrix |
| Scheduling | Live one-run health check survived restart, executed and delivered once to Matrix; job is now disabled |
| Voice, structured entity memory | Deferred |

The PoC shares `@homelab:pentagonlab.org` with monitoring at the user's request. Its private,
unencrypted **Hermes** room is `!LMCcDgGWyHMjEWvlWK:pentagonlab.org`, with
`@vladjik:pentagonlab.org` authorized. A dedicated account remains an optional later separation.
The host currently cannot enforce Docker memory limits; configured limits are advisory.

## Components and boundaries

```text
Matrix / GLM ← egress → Hermes → MCP stdio bridge → flowforge-gateway
Matrix ← egress → trusted approval listener ───────────────┘
                                      gateway ├─ Knowledge Router CLI + read-only vault
                                              ├─ private upstream → FlowForge planning API
                                              └─ operations network → Docker broker
```

No new component publishes a host port. Hermes cannot reach the Docker operations network
or the FlowForge upstream network. The gateway has no internet egress. The approval listener
has only its own Matrix credential and the approver credential; neither the broker nor
FlowForge credential is in that listener. Hermes receives only GLM, Matrix and gateway
credentials. It has no host checkout/home, SSH key, Docker socket or unrestricted shell.
Native file, terminal, code execution, browser, delegation and debugging tools are disabled;
Matrix/CLI/cron selections explicitly choose the personal MCP tools and selected native
memory/scheduling tools. Verify effective selections when upgrading Hermes.

Only the broker mounts Docker's socket. A `:ro` socket mount **does not prevent Docker API
writes**: the authenticated narrow handler and network isolation are the protection. This
trusted broker implements only allowlisted inspect/log/restart, never arbitrary paths,
container creation or exec. Do not connect untrusted containers to its network. It trusts
the gateway to enforce approval and durable write-audit policy.

The planning API has read-only source mounts, private plan output state and a GLM key. See
[FlowForge deployment boundaries](../flowforge/README.md). It does not use the production
FlowForge `.env` or mutate the production task queue.

## Configuration and deployment

From `apps/hermes`, use the private `.env` based on `.env.example` (mode 600).

- `HERMES_IMAGE`: pin the tested ARM64 image by digest after acceptance.
- `GLM_API_KEY`: GLM Coding Plan key. The example uses `zai`, `glm-5.3` and the global Coding Plan endpoint; change it for your account/model.
- `MATRIX_ACCESS_TOKEN`: the bot token, currently the shared homelab account.
- `MATRIX_ALLOWED_USERS`: comma-separated user IDs permitted to trigger/approve requests.
- `MATRIX_ALLOWED_ROOMS`: rooms available for interaction.
- `MATRIX_HOME_ROOM`: one exact room ID for scheduled results and approvals.
- `GATEWAY_TOKEN`, `APPROVER_TOKEN`, `BROKER_TOKEN`, `FLOWFORGE_TOKEN`: four distinct random tokens, at least 32 characters. Generate with `openssl rand -hex 32`.
- `DOCKER_GID`: host socket group from `stat -c %g /var/run/docker.sock` (984 on this host).
- `FLOWFORGE_URL`: `http://flowforge-api:8082`.
- `KNOWLEDGE_ROUTER_PATH`, `CODING_VAULT_PATH`, `FLOWFORGE_PATH`, `MENTORY_PROJECT_PATH`, `OPENCODE_BINARY`: existing source paths, documented in the example.

Build the Mentory source projection using the refresh command in **Knowledge scope, audit and metrics** below.
Create `data/hermes`, `data/flowforge-gateway`, `data/matrix-approvals` and
`data/flowforge-api`. The three custom-service state directories must be writable by
UID/GID 1000 with mode 700. Build the existing Knowledge Router with its own `npm ci` and
`npm run build`; its pure-JavaScript runtime dependencies and `dist` must be available.
Do not overwrite an existing `.env` with the example: it contains live credentials.

```bash
docker compose config --quiet
docker compose build flowforge-gateway matrix-approvals flowforge-api homelab-broker
docker compose up -d
docker compose ps
```

MCP SDK 2.x uses `MCPServer`; the bridge also supports v1's `FastMCP`. Hermes filters its
child-process environment: `mcp_servers.personal.env` explicitly forwards only the gateway
token and URL using native interpolation. A direct bridge test alone misses this boundary.
Core configuration, identity and bridge files are read-only mounts.

To change the scheduled-delivery room, edit `MATRIX_HOME_ROOM` and run
`docker compose up -d --no-deps hermes matrix-approvals`. `/sethome` tries to save the
read-only configuration and is not supported in this deployment. The environment setting
uses native Hermes delivery and persists across recreation. Encrypted rooms and voice
transcription require a later Hermes-native provider/encryption setup.

## Matrix approvals

A CONFIRM operation returns `APPROVAL_REQUIRED` with an ID and ten-minute expiry. It does
not execute. The trusted listener posts the gateway's exact tool and arguments as a notice
in the Hermes room, and adds two native reaction controls beneath it:

- Tap **✅** to approve the exact proposed action.
- Tap **❌** to reject it.

There is no need to copy an ID. The first valid decision takes effect immediately;
removing a reaction does not undo an already accepted action. Bot-seeded controls never
authorize execution themselves. The signed reaction must come from the allowed user and
point to that exact pending, unexpired prompt. Other messages/reactions cannot authorize it.

Text commands remain a fallback:

```text
!approve APPROVAL_UUID
!reject APPROVAL_UUID
```

Tap a reaction or send the chosen command from the authorized personal Matrix account in that room. Plain
“yes”, bot messages, another user/room, edited/redacted messages, old commands and unknown
IDs cannot approve an action. A timeline gap causes commands to be skipped for safety.
The prompt is sent independently from the agent, with a stable Matrix transaction ID;
the listener checks that the room is unencrypted before every send. Oversized proposals
are never truncated into an approval prompt: they require review through the operator API.

The listener records the Matrix sender, room, decision event and prompt event with the
gateway. It then executes the exact stored action once. Gateway approval state is consumed
durably before the effect; a crash or ambiguous outcome is reported for review, never
blindly replayed. Results return through the listener. For planning runs, the listener
polls that specific run and posts completed plans in bounded messages. It does not run
another planner or schedule business workflows. Existing cron jobs are untouched.

The agent cannot grant approval and should not resubmit or retry a pending write. Approval
commands belong to the listener; Hermes should leave their execution to it. A plain chat
reply claiming to be the user is not evidence of approval.

Operator CLI fallback remains available:

```bash
docker compose exec flowforge-gateway node /integration/operator.mjs
docker compose exec -e OPERATOR=your-name flowforge-gateway node /integration/operator.mjs APPROVAL_UUID approve
```

The fallback marks approval only; Matrix-approved requests are executed automatically by
the listener. Run one gateway and one listener replica; file state is not a distributed lock.

## Stable tool API

Except `/health`, endpoints require the gateway bearer credential. Tool calls also require
percent-encoded `X-Session-Id` (max 200 characters) and `X-User-Request` (max 2000). These
are agent-supplied audit annotations, not authenticated Matrix identity. Approval decisions
use verified Matrix event metadata from the separate trusted listener.

| Method/path | Input | Permission |
| --- | --- | --- |
| GET `/health` | — | unauthenticated process liveness |
| POST `/knowledge/search` | `{query,project?,scope?,limit?}` | READ |
| GET `/flowforge/workflows` | — | READ |
| GET `/flowforge/tasks` | — | READ |
| POST `/flowforge/run` | `{workflow,input}` | workflow policy; task-analysis is CONFIRM |
| GET `/flowforge/runs/:id` | — | READ |
| GET `/homelab/services/:name` | — | READ |
| GET `/homelab/services/:name/logs` | `lines=1..500`, optional ISO `since` | READ |
| POST `/homelab/services/:name/restart` | `{}` | service policy |
| GET `/metrics` | — | authenticated metrics |

Approval administration uses the separate approver credential: GET `/approvals`, GET
`/approvals/:id`, POST `/approvals/:id` with decision/operator and optional verified Matrix
metadata, POST `/approvals/:id/execute` for the exact stored approved action, and GET
`/approvals/:id/workflow` for that action's associated planning run. None is a model tool.

All supported service restarts require confirmation except Homepage, which is DENY. An
operator may explicitly designate a low-risk service AUTO_SAFE after local review.
Task-analysis input requires `project:"mentory"`, a discovered `task_id`, its exact
`task_sha256` and optional concise knowledge context. Run discovery before proposing it.
No arbitrary workflow, shell, Docker exec or host file mutation is exposed.

Success is `{success:true,data:...}`; failures use `{success:false,error:"CODE",message?:...}`.
Approval-required is a tool-level failure with HTTP 200. Other errors use 4xx/5xx. Inputs
are limited to 64 KiB; upstream results to 128 KiB; normal upstream calls to 30 seconds.
Long planning jobs acknowledge promptly and expose status. No automatic write retries.

## Knowledge scope, audit and metrics

`project:"mentory"` searches the existing Knowledge Router against a generated, read-only
Mentory vault. `project:"default"` retains the existing coding-guidance vault. Mentory
sources are README.md, SUMMARY.md and Markdown siblings of tasks marked `done` in the
production queue. Upcoming/failed tasks, agent prompts, source code, environment files and
arbitrary repository paths are excluded. Task completion is queue metadata, not independent
verification that every planning statement was implemented.

The projection adapts source layout to the existing router's skill/reference format; it
implements no ranking or search. Original project-relative paths, line ranges, SHA-256,
record kinds and task status are returned under `result.source`. Cite `source.reference`;
`result.path` and its line range refer to the projected vault. Planning, requirements,
execution records and explicit decision documents are labelled separately. No matches do
not establish that no decision exists. There is no separate ADR archive configured.

Refresh explicitly after relevant source changes, before deploying the gateway initially:

```bash
node scripts/build_mentory_knowledge.mjs \
  --project /home/pentagon-admin/Documents/apps/mentory \
  --queue /home/pentagon-admin/Documents/apps/flow-forge-tui/tasks.jsonl \
  --output /home/pentagon-admin/Documents/homelab/data/knowledge-mentory
```

Requires Node 24+. Run from the homelab root as the same UID as the gateway (1000). It
reads sources without modifying them, caps each document at 128 KiB and the snapshot at
16 MiB/2,000 documents, rejects symlinks/escapes, and atomically switches a content-addressed
snapshot pointer. The gateway only mounts this projection, read-only; it receives no source
repository or production queue mount. Missing/broken snapshots fail explicitly rather than
falling back to coding guidance. Snapshot IDs isolate index caches, so refreshes never reuse
an older index. Existing snapshots remain on disk for audit/review; automatic retention is
not implemented. Results expose the generation date; changes after refresh are not indexed.

`scope` remains router path hints, not a filesystem access boundary. The CLI uses argv
rather than a shell, a minimal child environment and an external cache under gateway state.

`data/flowforge-gateway/audit.jsonl` has durable start/final events, timestamp, session,
request, tool, arguments, result, approval flag, duration and verified approval evidence.
An unavailable audit sink blocks execution. Count final events rather than start events
when counting completed calls. Pending/terminal approval records preserve exact arguments
and outcomes in private state. Credentials must never be passed in tool arguments.

Known credentials, sensitive key names, bearer strings, common assignment patterns and
private key blocks are redacted. The broker strips known container-env secrets from logs
and omits full Docker environment, labels and mounts. Arbitrary unlabeled secrets cannot
be recognized reliably; applications must avoid logging them at the source.

Gateway metrics include tool calls/errors/duration, approvals and workflow submissions.
Counters reset on restart. Agent request and scheduled-run metrics remain native Hermes
state/logs; no unified exporter, automatic archive retention or backup-success API exists.
Backrest container health is not proof that backups succeeded. Monitor state disk use and
back it up with existing tooling; do not change its timers as part of this PoC.

## Verification

From the homelab root with Node 24+:

```bash
cd apps/flowforge-gateway && npm test
```

From the homelab root:

```bash
python3 -m unittest discover -s apps/flowforge -p 'test_*.py'
```

From `apps/hermes`:

```bash
docker compose exec -T hermes python - < ../../scripts/verify_hermes_tool_registration.py
docker compose exec -T hermes python - < ../../scripts/verify_hermes_mcp.py
docker compose exec -T flowforge-api python3 - < ../../scripts/verify_flowforge_preflight.py
```

The first container check uses Hermes' actual launcher/environment filtering and Matrix
tool selection; the second performs a real MCP handshake and read-only Vaultwarden call.
The 22 gateway/approval tests use fake local backends; four additional project-projection
tests cover source boundaries, refresh/citations, and the actual existing Knowledge Router CLI. The FlowForge integration test reuses the
actual existing runner with only the OpenCode process boundary mocked.

Live acceptance reports are kept locally under `reports/hermes-*-acceptance.md` and excluded
from Git because they contain private project/task details and Matrix event metadata.
A genuine approved planning run still requires a decision from the authorized Matrix user;
a test fixture or agent-authored “yes” cannot substitute for that.

## Upstream references

Checked on 2026-10-21; installed runtime source is used to verify version-specific behavior:

- [Hermes Docker and ARM64](https://hermes-agent.nousresearch.com/docs/user-guide/docker/)
- [Native Matrix adapter](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/matrix/)
- [MCP integration](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp/)
- [Native scheduled tasks](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron/)
- [Z.AI provider](https://hermes-agent.nousresearch.com/docs/integrations/providers/)

Approval reactions use standard [Matrix m.reaction annotations](https://spec.matrix.org/v1.16/client-server-api/#mreaction), so the existing Matrix client renders the controls.
