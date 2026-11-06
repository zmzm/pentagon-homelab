# FlowForge read-only inspection extension

Status: implemented, tested and deployed after explicit user authorization on
2026-10-26. The source-phase checks below preceded deployment. No model calls,
Matrix test events or production task operations were performed.

## Behavior

Six additive MCP tools expose registered-project discovery, effective project
configuration, host workflow/agent metadata, production queue records, existing
FlowForge doctor and directory-source sync preview. They use the existing
FlowForge reader functions, not a new planner or task lifecycle.

The gateway authorizes project reads with optional `flowforgeReadProjects`;
absence denies project reads. The reader independently checks
`FLOWFORGE_READ_PROJECTS`. Both default configurations permit Mentory only.
Existing workflow discovery still returns gateway-authorized workflows; the
host catalog cannot grant execution. Planning remains Mentory `task-analysis`
with exact task hash and existing Matrix approval.

`flowforge-inspect` is separate from the planning worker, on upstream only,
with read-only mounts, no writable state, no Docker socket, no model/Matrix/
planning credential and no host session DB. Its own token must differ from the
other configured tokens; child processes receive no API credentials.
Requests select fixed read functions with a 20-second child deadline and
120 KB output limit. Metadata is allowlisted/bounded and gateway-redacted.

Queue records do not establish a live worker; lock/session observation is
unavailable. Status includes counts, a marked 50-record window and unknown-state
count. Doctor reports the inspection environment only. JSONL sync preview is
inapplicable and returns `applied:false`; directory-source previews never apply.

## Validation observed

| Check | Result and scope |
| --- | --- |
| `python3 -m unittest discover -s apps/flowforge -p 'test_*.py'` | 18 passed, no skips; real external runner/readers on temporary projects, mocked planning process boundary, local HTTP and mounted-module subprocess tests |
| Node 24 `--test test/*.test.mjs` in gateway | 148 passed, no skips; localhost/Unix fixtures, policy/auth/audit, existing approval/restart/delivery regressions and temporary knowledge projections |
| MCP bridge tests | 5 passed in disposable installed Hermes image with network disabled and test source mounted read-only; system Python lacks Pydantic, so that interpreter could not run them |
| `scripts/verify_hermes_skills.py` without `--live` | Passed: installed Hermes registered 15 personal MCP tools and selected them in CLI/Matrix/cron; prohibited tools absent, native skill loading preserved; production container states and native skills/memory hashes unchanged during this check |
| Read-only container fixture | All six reader actions passed using installed FlowForge image with proposed inspector code, copied module set and temporary fixture mounts. Actual filesystem writes to source, agent library, queue and new state were denied; fixture hashes unchanged |
| Compose configuration | Passed with an ephemeral inspection-token placeholder; private `.env` was not changed and the real new credential has not been created |
| Python syntax and `git diff --check` | Passed |
| Existing production homelab projection `--check` | Expected not-ready: `sourceChanged:true` after documentation changes. Pointer retained; no production projection refresh |

Socket-based tests required running outside the network-restricted sandbox;
fixtures used only local sockets. No live model/Matrix behavior or deployed
inspection reachability was tested. The external FlowForge working tree was
read without editing its existing uncommitted changes.

## Compatibility and activation

Affected consumers: MCP bridge/configuration, gateway HTTP/policy/executor,
new inspector and existing FlowForge read functions. Native registration/smoke
scripts now expect 15 tools; the smoke script checks the six new read contracts.
Planning API/worker and Matrix relay contracts remain unchanged. Broker operation
contracts are unchanged, but its strict shared policy reader also needs the new image.
No persisted format changes: retained planning runs, approvals/audit, delivery
records, production queues/artifacts and Hermes native state remain readable.
The inspector adds no persisted records. Rollback must remove the six new MCP
include entries and the new policy field before starting the old strict gateway/broker
policy readers; preserve current state rather than restoring old execution claims.

Reviewed activation procedure, subsequently authorized and performed:

1. Create an independent `FLOWFORGE_INSPECT_TOKEN` in private configuration.
2. Prepare the missing operator-owned directories observed on this host:
   `/home/pentagon-admin/.config/flowforge/workflows` and
   `/home/pentagon-admin/.local/state/flowforge`. Their binds disable Docker's
   automatic host-directory creation.
3. Review native-path mounts and allowlists. Host `config.json` is currently
   absent, so bundled empty inspection defaults match this installation. If
   central defaults are added, set `FLOWFORGE_DEFAULTS_FILE` to that exact file.
4. Build/start `flowforge-inspect`, rebuild/recreate `pentagon-gateway` and
   `homelab-broker`, reload
   Hermes for the 15-tool include/bridge/SOUL. Leave planning worker, relay,
   production FlowForge schedules and application services untouched.
5. Run native registration and read-only MCP smoke, then explicitly refresh/check
   the existing homelab projection and verify original-source retrieval. No paid
   planning run, queue mutation or Matrix user event is required.

The native FlowForge checkout directory bind keeps atomic queue replacements
visible; the top-level legacy `.env` is masked. This is filesystem read access
to the configured checkout, not only its queue. The API exposes selected
metadata, and the planning worker receives none of those new mounts. Other
registered projects need explicit native-path read-only mounts and both
allowlists; registration alone does not expose them.

## Deployment and read-only acceptance

The user explicitly authorized the required restarts and setup after reviewing
the source/test work. No repeated approval was requested.

- Preparation found zero live approvals/execution claims, zero relay deliveries,
  no RUNNING planning records, zero Hermes active agents/turn leases, and one
  disabled cron job. Production queue: 91 done, 32 todo, no running/failed tasks.
- Added one independent inspection token to the existing private `.env` using an
  atomic write, retaining other credentials and mode 0600. Created operator-owned
  workflows and state directories; central config.json remains absent.
- Initial image build exposed a missing `.dockerignore` allow entry for
  inspector.py; corrected it before starting services. Added the native OpenCode
  binary path mount for Mentory's registered preflight setting.
- Built and started `flowforge-inspect`; rebuilt/recreated `homelab-broker` and
  `pentagon-gateway`, then force-recreated Hermes with existing native state.
  Broker is included because it shares the strict policy reader; an old broker
  image would reject the new policy key on a later restart.
- Gateway reached its Docker healthcheck. Direct inspector requests passed for
  all six operations, including doctor `ok:true`, zero issues, 11 agents (two
  disabled), queue counts 91 done/32 todo, and JSONL preview `applicable:false`,
  `applied:false`.
- Deployed native registration passed for all 15 tools and CLI/Matrix/cron
  selections; prohibited tool groups remained absent and curated skill loading
  matched the existing mount.

Docker reported that this host cannot enforce Compose memory limits. The
inspection deadline/output limits and read-only mounts remain in use; no claim
is made that the configured memory limit is enforced.

### Final deployed checks

- Deployed read-only MCP smoke passed: policy discovery, Vaultwarden inspection
  and all six inspection tools through Hermes → gateway → inspector. No approval
  was created. Existing planning workflow/task discovery also passed; gateway
  still exposes only `task-analysis` with CONFIRM. Its eligible planning list was
  empty under the existing month gate, with ten upcoming tasks returned; this is
  separate from the 32 production todo records visible through project status.
- Hermes native state reports gateway running, Matrix connected and API server
  connected. Gateway is healthy; all stack containers are running with zero
  restart counts at inspection. No model turn or Matrix test event was needed.
- Refreshed the existing homelab projection to snapshot
  `c5fd851e2eb4cdf765ff4b701220c0625fd3968df75a60159b9d0cbf39b522c1`.
  Read-only freshness check passed with `ready:true`, `sourceChanged:false`,
  `stale:false`. The snapshot records the existing Git revision and
  `documentationDirty:true`; source changes have not been committed by this task.
- Real gateway knowledge search retrieved the new project-inspection runbook
  with original citation `apps/hermes/README.md:686` (lines 686–752). Its source
  SHA-256 matched the current local README. Existing snapshots were retained.
- Compared against pre-deployment baseline: production queue, agent library,
  all four approval records, all four planning status records and retained relay
  prompts were unchanged. The original audit prefix was preserved, with new
  read calls appended.
- Native skill content, memories, all 17 session IDs, 222 stored messages and
  cron job configuration were preserved. No session reset or queue reset occurred.
- Exactly Hermes, gateway and broker container IDs changed; only the inspector
  was added. The planning API, relay and unrelated application containers kept
  their IDs. Planning and production schedules were not restarted.
- Runtime Docker inspection confirmed inspector rootfs and all source mounts are
  read-only, its only token/key environment entry is `FLOWFORGE_INSPECT_TOKEN`,
  it has no Docker socket and it joins only `personal-agent_upstream`. Hermes
  has none of the inspection/planning/broker/approver tokens.

Deployed image IDs:

| Component | Image |
| --- | --- |
| Inspector | `sha256:4bacd296eda7da75da3dd05e158a0c24f9d942aa604012d8963813e7c3d85398` |
| Gateway | `sha256:4f19ef2f401dcd00ec46eb2ffc8cd708bc127426d68eda51f1c7875cb8b38eeb` |
| Broker | `sha256:f145042ae55bcbff067e31da070bf7c038c500240aa172c186131f519a8f7183` |
| Hermes, retained image | `sha256:2f305c9bdc81731f48664586d23cb6a6f838a15ad7be1bfabe0c3c269d8e09b9` |

These checks establish deployed read-only tool integration and retrieval, not a
new model-driven conversational/Matrix acceptance or paid planning/execution run.
