# Hermes personal runtime PoC

Hermes owns Matrix conversation, sessions, lightweight memory and new conversational
schedules. The gateway owns the stable tool API, permission policy and audit. Knowledge
Router owns retrieval; FlowForge owns planning/workflows. Production FlowForge timers,
monitoring and existing application services remain independent.

## Status

| Capability | Implementation and verification |
| --- | --- |
| Matrix + GLM | Running; a real authorized Matrix request inspected Vaultwarden, read logs and returned an answer |
| Personal MCP tools | Nine tools verified through native registration and effective CLI/Matrix/cron selections; read-only discovery and Vaultwarden tool chain tested |
| Service discovery | Deployed 2026-10-22: policy-backed configured tool coverage, with identifiers and informational restart levels; no Docker query or runtime health claim |
| Permissions | READ/AUTO_SAFE/CONFIRM/DENY; exact-action, durable single-use approvals; no model approver credential |
| Matrix approvals | Separate trusted listener posts exact actions and accepts commands or seeded reactions only from allowed Matrix users in the configured room; security tests pass |
| Knowledge Router | Existing router searches coding guidance, completed Mentory task records/history, and a separate allowlisted homelab documentation snapshot; homelab deployment/refresh is explicit |
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
memory/scheduling tools plus native skill discovery/loading. Verify effective selections
when upgrading Hermes.

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

Build the Mentory and homelab source projections using the refresh commands in
**Knowledge scope, audit and metrics** below before starting the gateway.
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

## Curated native skills

The installed image was inspected on 2026-10-22: **Hermes v0.22.3 (2026.9.24),
upstream `5b147ab0`**, image ID
`sha256:2f305c9bdc81731f48664586d23cb6a6f838a15ad7be1bfabe0c3c269d8e09b9`.
The source inside that image, rather than a newer upstream configuration example,
defines this integration:

| Installed source | Behavior used here |
| --- | --- |
| `agent/skill_utils.py:get_external_skills_dirs/get_skill_search_roots` | Reads `skills.external_dirs`; trusted project, local, create-dir, then external precedence; name collisions can shadow an external skill |
| `tools/skills_tool.py:skills_list/skill_view/check_skills_requirements` | Native metadata discovery and full loading; read tools are always available, with no terminal/file/browser/delegation requirement |
| `agent/system_prompt.py:_skills_prompt`, `agent/prompt_builder.py:build_skills_system_prompt` | Native name/description index is presented when skill tools are offered; the model selects a skill with `skill_view` (or a user explicitly preloads it) |
| `toolsets.py`, `model_tools.py`, `hermes_cli/tools_config.py` | Platform selection resolves groups, subtracts disabled groups, then filters actual tool schemas by availability |
| `agent/oneshot_footprint.py` | Finite CLI queries hide `skill_manage`; interactive Matrix sessions do not, so a CLI-only check would miss it |
| `agent/skill_preprocessing.py`, `pm/install.py` | Inline shell is optional and off; loading a skill with `deps` can otherwise attempt lazy installation |

`skills/homelab-service-diagnosis/SKILL.md` is the single curated skill. Compose
mounts `./skills` at `/opt/hermes-curated-skills:ro`; `skills.external_dirs` adds
it to native discovery. It does **not** replace `/opt/data/skills` or change the
existing writable `/opt/data` memory/state mount. The skill has no scripts,
package dependencies, secret requirements or execution requirements.

The installed `skills` group also includes **`skill_manage`**, an authoring tool
unneeded for this task. This version has no config-only per-native-tool filter.
The small, read-only mounted `plugins/homelab-skill-tools` defines
`homelab-skills-read` through the installed `toolsets.create_custom_toolset` API,
containing exactly `skills_list` and `skill_view`. It adds no handlers, tool
overrides, shell hooks or model execution capability. This helper uses a
version-specific core import rather than a stable `PluginContext` method;
revalidate it against the installed source on upgrades. If it fails to load,
the custom group does not resolve; do not fall back to enabling all skills.

CLI, Matrix and cron select that narrow group. Existing memory/scheduling/MCP
selections remain. `skills.inline_shell:false` prevents shell expansion during
loads, `security.allow_lazy_installs:false` prevents automatic acquisition of
skill dependencies, and `curator.enabled:false` prevents background skill
maintenance. Neither terminal, general files, code execution, browser nor
delegation is enabled. Native reads can update Hermes' own skill usage/cache
metadata under writable state; this does not grant the model file-writing tools.
The existing MCP write tools remain available for separately requested actions;
the skill and SOUL explicitly prohibit invoking them or creating approval
requests during diagnosis. This is a procedural boundary, not a new gateway
permission class or a hard per-request removal of write tools.

The procedure discovers configured coverage when a target identifier is unknown
or coverage is needed, clarifies genuinely ambiguous services, inspects state,
reads a bounded log tail when useful, and searches `project="homelab"`. Discovery
cannot choose a target on the user's behalf; restart levels do not grant approval.
Its English reply leads with
a short plain-language assessment, distinguishes observed facts from documented
guidance and labelled hypotheses, and explains the useful next step and material
verification limits. Routine replies use readable source labels; exact file/line
references and technical details are supplied when useful or requested. Native
tool results retain the full evidence and original documentation references.

Installed `gateway/display_config.py` and `gateway/run_turn.py` support the
Matrix-specific `display.platforms.matrix` settings used here: `tool_progress: log`
keeps tool-progress messages out of chat and writes them to the native rotating,
redacted `logs/tool_calls.log` under the Hermes home (5 MiB × 3). Native session
tool results and gateway audit remain available. `interim_assistant_messages: false`
hides intermediate schema/skill commentary; `show_reasoning: false` keeps reasoning
hidden. These are presentation settings, with no additional tool permissions.
The gateway resolves display settings for each turn. A continuing conversation
can still reuse its saved system prompt and previously loaded skill content;
verify revised writing instructions in a fresh user-controlled session. In
Matrix, send standalone `!new` without a mention/display-name prefix, choose
**Approve Once** if prompted, and wait for the reset confirmation before testing.
Keep the confirmation guard enabled. The operator must not send these events
on the user's behalf. Refresh the homelab knowledge snapshot after publishing
changes to its allowlisted documentation, using the refresh procedure below.

### Skills validation and rollout

Run the offline installed-image checks from the repository root:

```bash
python3 scripts/verify_hermes_skills.py
```

This uses the live container's exact image ID with networking **disabled**, fake
gateway credentials, a disposable tmpfs Hermes home and a copy of only the
existing skills. It mounts the proposed configuration/curated skill/helper,
registers all nine MCP schemas through Hermes' native subprocess
environment, checks effective CLI/Matrix/cron schemas (including prohibited
tools and absence of `skill_manage`), and verifies the native prompt index,
`skills_list` and `skill_view` resolve the expected mounted skill and exact bytes.
It compares production container IDs/start times and skill/memory file hashes
before/after, then removes the test container. No Matrix adapter is started.

Live behavioral acceptance is a separate, explicitly approved external-data
egress step:

```bash
python3 scripts/verify_hermes_skills.py --live
```

It forwards only the existing GLM/gateway credentials, keeps Matrix credentials
absent, and asks three fresh CLI sessions to diagnose Vaultwarden, clarify an
ambiguous Matrix target, and discover configured coverage without choosing a
target. It retains all existing tool schemas. A validation-only
copy of the MCP bridge blocks any HTTP call other than policy discovery, diagnostic service reads
and `project="homelab"` retrieval before reaching the real gateway; any blocked
attempt fails acceptance. Native `skill_view` selection, inspect/log/search
calls, bounded log requests and absence of write-tool calls are checked from
the isolated session database. The coverage case must call discovery and ask
for a target without inspecting one. Inspect the saved English answer and tool
results manually: ensure the answer is readable without internal tool names,
raw fields or snapshot metadata; state claims match runtime evidence; documented
guidance is attributed clearly and traceable to original `source.reference` and
`source.kind` in the retained tool results; hypotheses are labelled; and
unverified reachability/backup success is not asserted. Source/answer separation
is semantic review, not a keyword-only assertion. Successful native loading by
itself does not prove model selection or answer quality.

Private evidence is stored in Git-ignored
`reports/hermes-skills-static-evidence.json` / `reports/hermes-skills-evidence.json`.
The offline command covers configuration selection for CLI, Matrix and cron;
`--live` covers CLI behavior only. Neither proves end-to-end Matrix behavior.
After approved deployment, repeat an authorized diagnostic request in Matrix
and inspect the native session/tool trace and gateway audit for no writes or
approval creation. Do not use a real restart as a diagnostic test.

Initial installation requires operator deployment to add the mounts and load
the plugin. From `apps/hermes`, after validation/review, recreate only Hermes
when deployment is needed:

```bash
docker compose config --quiet
docker compose up -d --no-deps --force-recreate hermes
docker compose exec -T hermes python - < ../../scripts/verify_hermes_tool_registration.py
```

Recreation adds the two mounts and loads the plugin/configuration/SOUL. The
existing runtime skills and writable memory remain mounted. Do not recreate
the gateway, broker, Matrix services or other applications for the initial skill
installation alone. The discovery API addition also needs the gateway rollout
described under [Service discovery and rollout](#service-discovery-and-rollout) below.
Because this README is in the homelab documentation allowlist, refresh/check
the homelab knowledge projection with the documented host commands when
publishing the updated documentation. Projection refresh needs no restart.

2026-10-22 latest acceptance covers **isolated CLI and real Matrix behavior**.
Native discovery/loading and effective CLI/Matrix/cron permission checks passed.
The configured GLM provider selected the skill and used service inspection,
100-line logs and `project="homelab"` retrieval. An ambiguous Matrix target
produced a question with no personal MCP calls before an actual user choice.
No diagnostic write or approval request was attempted. Manual review and user
feedback accepted the short English Matrix reply; technical progress stayed in
private logs. The final Matrix turn loaded the exact current curated skill.
See [the sanitized deployment and acceptance report](../../reports/2026-10-22-hermes-skills.md)
for evidence, earlier failures, a minor wording limitation and rollout details.

The isolated CLI ambiguous case also stopped when native clarification was
unanswered/undelivered, with no personal MCP calls. Its validation guard and
production isolation remained intact. The initial integration deployment
recreated only Hermes and preserved memory/runtime skills; subsequent writing
and display changes used the existing mounts and required no further restart.

This fixes an earlier live failure in which the model followed the native
one-shot clarification fallback and inspected guessed targets. The skill and
SOUL now require an actual user choice and explicitly stop on failed,
unavailable or unanswered clarification, even if a tool notice suggests making
an assumption. The same failed trace remains rejected by the checker; the
previous evidence/report is retained locally under
`reports/hermes-skills-before-clarification-fix-*`.

The harness was corrected to give its tmpfs home private UID/GID 10000 ownership,
read that home as the same unprivileged observer, retain failed CLI output
privately, and validate underlying calls inside native `tool_call` batches.
Eight regression tests cover direct/deferred calls, nested writes, unanswered
clarification, missing final questions, coverage discovery without target
selection, and the validation HTTP guard. Before the discovery addition, the
latest live command exited successfully with complete native observations and
both final answers in private evidence; no trace recovery was needed. See
`reports/hermes-skills-acceptance.md` locally. This is one observed passing run,
not a guarantee of all future model behavior; deployment and end-to-end Matrix
acceptance remain separate steps.

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
polls that specific run and delivers completed plans as described below. It does not run
another planner or schedule business workflows. Existing cron jobs are untouched.

### Planning result delivery

A completed run produces one deterministic English notice with its task ID, run ID,
outcome and available plan filenames, followed by `concept-plan.md` and
`grounded-plan.md` as complete UTF-8 Markdown `m.file` attachments. There is no model
summary or inferred conclusion. Failed runs produce only a short notice with the
task/run IDs and error code, without dumping outputs or tracebacks.

The only source is the authenticated gateway's GET `/approvals/:id/workflow`
response, after gateway redaction. The relay never reads raw FlowForge files and
needs no source/output mount. It uploads these sanitized bytes through Matrix's
media API using the existing `MATRIX_ACCESS_TOKEN`, then sends the file events to
`MATRIX_HOME_ROOM`. The room must remain unencrypted; uploads and sends check this.

Delivery progress lives in `data/matrix-approvals/matrix-approvals.json` under each
prompt's `workflowDelivery`: the frozen sanitized plans, notice/fallback bodies,
per-file upload status, Matrix media URI and acknowledged event IDs. Keep this
state volume and the existing Matrix account/token across restarts. Message retries
reuse the same transaction ID and content, following [Matrix transaction semantics](https://spec.matrix.org/v1.17/client-server-api/#transaction-identifiers).
An acknowledged upload is reused. POST media uploads have no transaction ID, so
the relay durably claims each attempt before sending. A timeout, server error,
invalid success response or crash before saving the media URI leaves the upload
`uncertain`; it is never automatically repeated. Explicit HTTP upload rejections
are recorded as failures. Rate-limit rejections alone retry automatically, at most
three attempts, respecting retry timing with a minimum 30-second delay.

If any attachment remains undelivered or a required plan is missing, delivery stays
`failed` and the listener sends one bounded fallback: at most 3,000 UTF-8 bytes per
undelivered plan, with explicit truncation markers. Complete available sanitized
plans remain in relay state. Failed deliveries are excluded from normal completed
prompt pruning. Confirmed files are not resent; unconfirmed message sends keep
retrying the same transaction, including after a restart. A fallback send failure
is also durable and retried; it never marks attachment delivery successful.

For operator recovery, stop the relay and back up its state before inspecting or
editing delivery records. For `uncertain` uploads, first determine whether Matrix
accepted the upload and recover its URI if possible; do not clear claims blindly.
If recovery cannot establish the outcome, retain the failure record and review the
full sanitized text in relay state. Do not attach raw files from `data/flowforge-api`.
Approval decisions and execution claims must remain intact; never resubmit the paid
planning run to repair delivery.

To deploy only this relay change using the existing environment and state volume:

```bash
cd apps/hermes
docker compose build matrix-approvals
docker compose up -d --no-deps matrix-approvals
docker compose ps matrix-approvals
docker compose logs --tail 50 matrix-approvals
```

No gateway, planner or broker rollout is required. Validate with the local gateway
test suite first; deploying the relay resumes pending deliveries without starting
another planning run. This delivery change has not been deployed or validated with
a paid workflow.

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

## Restart verification and rollout

An approved service restart consumes the same exact-action approval durably before
execution. The broker sends **one** Docker `POST /containers/:name/restart?t=10`.
Only after Docker acknowledges that request does it poll read-only container inspect.
Verification never sends another restart, including when inspection fails or times out.
The listener reports the outcome in concise English in the original Matrix room.

The Docker request has an absolute 15-second deadline, including response headers and
body. Verification then has a separate 10-second window, with inspect requests capped at
2 seconds or the remaining window, whichever is smaller, and 500 ms between starting
observations. The maximum nested operation budget is 25 seconds, leaving headroom inside
the gateway's 30-second broker request, the relay/MCP's 35-second requests and Hermes'
40-second tool budget. Synchronous execution therefore fits; no asynchronous execution
endpoint or extra execution retry is introduced. Slow health checks can outlast this window.

Example gateway result (also persisted in the approval's `outcome`):

```json
{"success":true,"data":{"service":"example-service","restarted":true,"restart":{"status":"acknowledged"},"verification":{"source":"docker","windowMs":10000,"elapsedMs":500,"attempts":2,"status":"healthy","observation":{"status":"running","running":true,"health":"healthy"}}}}
```

`verification.status` distinguishes:

| Status | Observed result |
| --- | --- |
| `healthy` | Container is running and Docker reports healthy. |
| `running_no_healthcheck` | Container is running with no configured health check (including explicitly disabled checks). |
| `unhealthy` | Container is running but Docker reports unhealthy. |
| `stopped` | Container is stopped or not in the running state, including paused containers. |
| `starting_timeout` | Docker still reported starting when the verification deadline expired. |
| `unavailable` | Inspect failed, timed out, returned invalid state, or arrived after the deadline. |
| `not_attempted` | The restart was not acknowledged, so verification was not attempted. |

Only a starting state is polled again. Healthy, missing-check, unhealthy and stopped
observations end verification immediately. An inspection error ends it as unavailable;
it does not reuse an older starting observation to claim a current state. The response
includes only selected state fields, never health-check output, environment or commands.

`success:true`, `restarted:true` and approval `DONE` mean Docker acknowledged the restart;
always read `verification.status` separately. They do not mean the application recovered
or is externally reachable. No network or application probe is performed here.

If Docker's acknowledgment or the broker response is lost, the gateway returns
`success:false`, `error:"RESTART_UNCERTAIN"`, `restarted:null`,
`restart.status:"uncertain"` and `verification.status:"not_attempted"`. The consumed
approval is stored as `UNCERTAIN`. A timeout is not evidence that Docker did nothing.
Neither gateway nor relay retries execution. A process crash can leave `CONSUMED`;
the existing relay also reports that as uncertain and never replays it. Inspect safely
before deciding on a separate, explicitly authorized action.

This change is tested with fake Docker, broker and Matrix backends only. Deployment is
a separate operator action; no service restart or rollout is part of these tests. Run
the gateway test suite with Node 24+ first. Before a later rollout, let in-flight approved
requests finish and preserve both gateway and relay state directories. From `apps/hermes`:

```bash
docker compose build homelab-broker flowforge-gateway matrix-approvals
docker compose up -d --no-deps homelab-broker flowforge-gateway matrix-approvals
docker compose ps homelab-broker flowforge-gateway matrix-approvals
```

Keep one gateway and one relay replica. Check their health and logs without submitting
a restart request. Do not replay consumed or uncertain approvals to validate a rollout.

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
| GET `/homelab/services` | — | READ; configured tool coverage from policy |
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

### Service discovery and rollout

Deployed and verified on 2026-10-22. The gateway was rebuilt and recreated, then
Hermes was recreated after gateway health passed. All nine native MCP tools and
effective CLI/Matrix/cron selections passed verification, as did a real MCP
discovery call and the existing read-only Vaultwarden inspection. Other
containers and the mounted policy were unchanged. See
[the deployment record and verification limits](../../reports/2026-10-22-homelab-service-discovery.md).
New live model behavior and end-to-end Matrix discovery have not been tested.

`homelab_list_services(session_id, user_request)` in the existing personal MCP
bridge calls GET `/homelab/services`. The shared `mcp-personal` group selects it
for CLI, Matrix and cron through the explicit MCP include list. It returns:

```json
{"success":true,"data":{"coverage":"configured_tool_coverage","services":[{"service":"example-service","restart":"CONFIRM"}]}}
```

The gateway derives the array only from its loaded `policy.services`, including
services whose restart level is DENY. An empty policy returns an empty array.
Each entry contains only the configured identifier and `restart` level
(`AUTO_SAFE`, `CONFIRM`, or `DENY`). This is configured tool coverage, not a list
of currently running or healthy services. Discovery makes no broker or Docker
request and returns no container names/configuration, secrets, host paths,
environment variables, workflows or project configuration. It requires the
normal gateway bearer credential and audit headers; it accepts no filters.
Restart levels are informational: authorization and confirmation are checked
again when a restart is requested. Discovery creates no approval or permission
grant and does not change any existing service policy.

The diagnosis skill discovers coverage when an identifier is unknown or coverage
is requested. Genuinely ambiguous targets still require clarification before
personal MCP calls. When discovery cannot resolve a target the user has chosen,
or the user has not chosen one, it asks and waits; it never substitutes a
configured service or chooses one merely because it is the only plausible entry.

For subsequent rollouts, source updates and fixture tests alone do not deploy
the change. After review, run the offline installed-image registration check above,
refresh/check the homelab knowledge projection because this README changed,
and deploy from `apps/hermes` using the existing private `.env` and policy:

```bash
docker compose config --quiet
docker compose build flowforge-gateway
docker compose up -d --no-deps flowforge-gateway
```

Wait for the gateway health check to pass, then recreate Hermes so its MCP
subprocess, include list and native skill are reloaded:

```bash
docker compose up -d --no-deps --force-recreate hermes
docker compose exec -T hermes python - < ../../scripts/verify_hermes_tool_registration.py
docker compose exec -T hermes python - < ../../scripts/verify_hermes_mcp.py
```

These commands are retained for subsequent operator rollouts; the deployment
record describes the completed rollout and exact checks performed.
No policy edit, new credential, broker restart or restart of Matrix or the
inventoried applications is needed for discovery. Registration verification expects
nine personal tools and checks effective CLI, Matrix and cron selections. The
MCP smoke check reads policy coverage before its existing Vaultwarden inspection.
Live model/Matrix behavioral acceptance remains a separate authorized step; do
not request a restart to test discovery or diagnosis.

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

### Homelab documentation

For homelab questions, call the existing `knowledge_search` with `project:"homelab"`.
This separate projection reuses the same CLI, snapshot publication and citation mapping;
it adds no retriever. Its explicit allowlist is:

- `README.md`, `ARCHITECTURE.md`, `SERVICES.md`, `DOMAINS.md`, `OPERATIONS.md`,
  `RECOVERY_CHECKLIST.md`, `monitoring/README.md`, `apps/hermes/README.md`
- `incidents/*.md` (direct, non-hidden Markdown files only; no recursive traversal)

All eight fixed documents are required; source errors abort the build before the current
pointer changes. No linked documents are followed. Ansible guides, reports outside
`incidents/`, other app docs, code, Compose files, runtime data, backups and credentials
are excluded. The gateway mounts only `data/knowledge-homelab` at `/vaults/homelab:ro`,
never the host homelab repository. Hermes accesses it only through the gateway.

Operational documents have `source.kind:"operational-document"`; incident reports have
`source.kind:"historical-incident"` and separate router skills. Historical references are
never attached to the operational skill. Incidents document past events, including their
then-current resolution/prevention advice; they do not establish current configuration or
instructions. Even operational docs are recorded documentation, not a live state check.
Use service inspection for current runtime evidence and report uncertainty when only
history matches. Preserve the original `source.reference`, line range and document SHA-256.
Projected paths/ranges remain in `result.path/startLine/endLine` for router compatibility.

From the homelab root, as UID 1000 with Node 24+, build/refresh after documentation changes:

```bash
node scripts/build_homelab_knowledge.mjs --project "$PWD" --output "$PWD/data/knowledge-homelab"
node scripts/build_homelab_knowledge.mjs --project "$PWD" --output "$PWD/data/knowledge-homelab" --check
```

The first command reads only allowlisted source contents and Git version/status metadata.
It bounds documents at 128 KiB and snapshots at 16 MiB/2,000 documents, rejects symlinks,
writes an immutable content-addressed snapshot, then atomically replaces `current.json`.
It leaves original sources untouched. An unchanged refresh reuses the snapshot and renews
the pointer's `refreshedAt` after re-reading the sources; `generatedAt` remains immutable.
Old snapshots remain for audit, with no automatic retention or new watcher/timer.
Each snapshot uses a distinct gateway cache, built by the existing router on first search.
Refresh after a documentation commit to record that committed revision.

The read-only `--check` exits 1 for missing/invalid snapshots, changed source/version or
snapshots last refreshed over seven days ago; exits 0 when current. It detects incident
additions/removals too. Search returns `sourceSnapshot` even on no matches, including ID,
manifest version, repository, `gitCommit`, `documentationDirty`, generation/refresh times,
age and `stale` (seven-day threshold). Unknown Git metadata is `null`, not a clean revision.
Missing/broken snapshots return `KNOWLEDGE_PROJECT_NOT_READY`; there is no fallback source.
Stale snapshots remain searchable with `stale:true` so the agent can identify the limitation.
The gateway has no live source mount, so `sourceChanges:"unknown"` explicitly means it
cannot detect edits since refresh. Run `--check` on the host for that comparison. A recent
snapshot is not proof that service state matches documentation.

For initial deployment after reviewing the change, build/check the projection and validate
Compose, then build/recreate **only** the gateway and Hermes from `apps/hermes`:

```bash
docker compose config --quiet
docker compose build flowforge-gateway
docker compose up -d --no-deps --force-recreate flowforge-gateway hermes
```

This picks up the new read-only mount, policy, MCP description and SOUL instructions.
Force recreation ensures Hermes reloads its bind-mounted instructions and MCP description
even when its image and Compose service configuration are unchanged.
Later documentation-only refreshes need no restart: each search reads the atomic pointer.
Do not recreate other services or change production schedules for this integration.

### Mentory refresh

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
python3 -m unittest discover -s apps/hermes -p 'test_*.py'
python3 -m unittest discover -s scripts -p 'test_verify_hermes_skills.py'
```

The Hermes bridge fixture tests require a Python environment with the MCP SDK
and Pydantic, as provided by the Hermes image. They use mocked HTTP responses
and make no request to deployed services.

From `apps/hermes`:

```bash
docker compose exec -T hermes python - < ../../scripts/verify_hermes_tool_registration.py
docker compose exec -T hermes python - < ../../scripts/verify_hermes_mcp.py
docker compose exec -T flowforge-api python3 - < ../../scripts/verify_flowforge_preflight.py
```

The first container check uses Hermes' actual launcher/environment filtering and
CLI/Matrix/cron tool selection; the second performs a real MCP handshake, policy
discovery and a read-only Vaultwarden call.
Gateway/approval tests use fake local backends. Projection tests cover source boundaries,
refresh/citations, source selection and the actual existing Knowledge Router CLI. The homelab
integration test asks about Matrix external exposure, database backups and the DNS loop
incident against the real repository docs, checking original citation content and kinds.
Set `KNOWLEDGE_CLI` to an alternate built CLI path if necessary; otherwise it uses the sibling
`../apps/knowledge-router/dist/cli.js` checkout. If absent, CLI tests explicitly skip;
fixture tests alone do not prove retrieval. This local CLI check does not prove deployed
Hermes/MCP acceptance. After deployment, ask those questions via `knowledge_search` with
`project:"homelab"` and verify source metadata. The FlowForge integration test reuses the
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
