# Matrix presentation deployment — 2026-10-25

Deployed the tested working-tree presentation changes at 2026-10-25T14:08:59.901218+00:00.
The user explicitly requested redeployment. This deployment does not create a
commit or reset user sessions.

## Scope and implementation

- Rebuilt `matrix-approvals` and recreated only `hermes` and `matrix-approvals`
  with `--no-deps --force-recreate --pull never --no-build`.
- Retained the installed Hermes image. Deployed relay source and mounted SOUL
  hashes match the tested working tree.
- New approvals use compact formatted notices and Approve/Reject text reaction
  chips; retained prompts keep their original control style. Exact proposal,
  sender/room/event checks, execution claims and command fallback remain.
- Gateway, broker and planning API container identities/start times remained
  unchanged. Persistent mount sources and access modes remained unchanged.

## Evidence

- Before deployment: no unfinished relay prompts, pending deliveries, upload
  claims, unsettled gateway approvals, running planning runs, active Hermes
  agents/sessions, or running conversational cron jobs.
- Created a private relay-state backup. Native memory, skills and cron-file
  hashes matched across recreation; retained relay prompt records matched.
- Hermes reports a live native gateway heartbeat and Matrix connected.
- Native registration passed for all nine personal MCP tools and the effective
  CLI/Matrix/cron selections; prohibited tools remain absent.
- Real MCP handshake, bounded schema checks, policy discovery and read-only
  Vaultwarden inspection through the gateway/broker passed.
- Relay module inspection returned `Approve` and `Reject`; deployed file hashes
  matched source. The implementation's 138 gateway regression tests passed
  before deployment using fake backends and local fixture servers.

## Caveats and acceptance limits

Startup emitted one `config-migrate` error because `/opt/data/config.yaml` is
intentionally mounted read-only. The gateway continued, Matrix connected, and
the effective configuration/tool checks passed. No other matching startup errors
were found in the bounded deployment log inspection. The config mount was kept
read-only.

Compose also reported that kernel/cgroup memory-limit capabilities were unavailable
for the recreated containers; the configured memory limits were discarded by
Docker. Resource configuration was not changed as part of this deployment.

No paid/model calls, Matrix user/approval events, or session resets were performed.
Native Matrix connection and source inspection do not prove actual client rendering,
reaction clicks, or end-to-end approval/delivery acceptance. Existing conversations
can retain saved wording until a fresh user-controlled session. No knowledge index
refresh was performed.

Private state and bounded logs are retained in ignored, mode-600 deployment evidence
and log files. Do not roll back to a relay without text-control support while new
approvals or unacknowledged sends are pending; preserve all execution/media claims.

## Emoji and text label update

At 2026-10-25T14:31:40.316340+00:00, the same two services were redeployed with
`controlStyle: text-emoji-v1`: **✅ Approve** and **❌ Reject**. Existing `text-v1`
and emoji-only prompts retain their original keys, including unconfirmed control
retries. All 139 gateway tests passed. The repeated deployment checks confirmed
Matrix connected, exact deployed source hashes, unchanged persistent mounts/native
memory/skills/schedules, and unchanged other service containers. Native registration
and the read-only MCP/gateway/broker checks passed again. The same protected-config
migration warning remains nonfatal; no additional startup errors were detected.

A separately recorded dummy UI test using the deployed relay and real Matrix
transport previously reached DONE with one no-op execution. It used an isolated
gateway fixture with no production executor calls, so it establishes a real
approval-reaction round trip for that demo rather than production gateway execution.
A fresh dummy prompt is being sent for client inspection of the combined labels.

## Request-style approval layout

At 2026-10-25T14:41:44.253523+00:00, only `matrix-approvals` was recreated. Hermes was
not restarted. The deployed `request-v1` layout leads with a direct request and
a fixed effect description for restart/planning/dummy actions, followed by the
original user request, exact tool name and every argument as visible labeled
fields. Structured values retain keys and scalar/container types. Only the
reference, exact UTC expiry and command fallback are in an expandable footer;
plain text retains all content. Warsaw-time expiry is also shown prominently.
Unknown tools receive no invented effect/safety summary.

New prompt records carry an additive layout marker; retained prompts keep their
previous rendering, and complete stored message payloads remain frozen before
dispatch. Approval decision and execution behavior did not change. A 60,000-byte
serialized-message guard complements the original source-size check without
truncating action details.

All 145 gateway tests passed, including nested-value preservation, HTML escaping,
byte bounds, old-layout compatibility and stable retries. Deployment checks
confirmed exact source hashes, visible action fields, Matrix authentication,
relay-to-gateway connectivity and no relay errors in the bounded startup log.
Native data and approval records were preserved; other service containers were
unchanged. Fresh client rendering is pending user review of a new isolated
dummy prompt. Earlier separate dummy runs reached DONE, which does not establish
production gateway action execution or acceptance of this new layout.
