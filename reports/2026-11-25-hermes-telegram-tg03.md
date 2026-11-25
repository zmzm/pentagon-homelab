# TG-03: Telegram security review and regression evidence

Historical review of TG-02 before remediation. The subsequent
[fix report](2026-11-25-hermes-telegram-tg03-fixes.md) records current remediation
and verification; findings and check counts below describe the reviewed revision.

Task: [TG-03](https://trello.com/c/74euTZQZ), reviewing
[TG-02](https://trello.com/c/9aNMlcit). The operator confirmed review of TG-02
only: `git diff 271d4be...49ddf84`, one commit,
`49ddf841beb8b1413c93f31e0b02165c25388fd3` (restricted native Telegram adapter).
The working tree was clean before this task. Standards and specification were
reviewed independently in parallel; findings below retain their separate axes.

**Review completed; deployment is blocked.** Regression tests reproduce access
gaps rather than claiming unconditional rejection. This change adds tests and
review/runbook evidence; it does not fix the native authorization paths or
deploy TG-02. No Trello write, image upgrade or production restart was performed.

## Standards

**One finding, P1: validate the user-list syntax before enabling Telegram.**
[Compose](../apps/hermes/docker-compose.yml) uses nonempty interpolation for
`TELEGRAM_ALLOWED_USERS`, which accepts `*`, `123456,*`, whitespace-only text,
usernames and negative chat IDs. The installed runtime treats `*` as universal
authorization even with platform/global allow-all flags false. Fixture Compose
rendering accepts these inputs; a native message from an unknown user passes
authorization when the list is `*`.

This conflicts with the mandatory runtime-input validation rule in the resolved
coding vault's `common/engineering/references/contracts-and-validation.md`.
The runbook's numeric-only instruction is a procedural check. Follow-up must
enforce nonempty positive decimal user IDs at startup, reject wildcard/malformed
entries before enabling the adapter, and add rejection regressions. The native
consumer is `gateway/authz_mixin.py` (`_principal_authorized`); Telegram's
`_env_allowlist_decision` also recognizes the wildcard. No material heuristic
code-smell findings were identified.

## Spec

**Two findings:**

1. **P2: group denial does not cover callbacks.** TG-02 requires “disable …
   group/channel access” and checking “alternate authorization paths.” The
   configured `group_allow_from: []` rejects group/forum/channel message intake.
   Native `_is_callback_user_authorized` delegates directly to the runner's
   platform authorization; an allowlisted user passes that check in a group.
   The new test proves both outcomes under the same configuration. Native model
   and choice picker callbacks use this separate gate; other consequential
   callbacks can also require matching pending state. This proves an incomplete
   authorization boundary, not an observed production exploit. Follow-up must
   reject non-DM callback contexts before dispatch and cover group/forum/channel
   callbacks, including allowlisted users and retained prompt state.
2. **P2: the explicit user allowlist permits open access through a wildcard.**
   TG-02 requires an “Explicit nonempty user allowlist” and disabling open
   access. The Standards finding also leaves this acceptance condition partially
   enforced. Numeric validation must become an enforced boundary; until then,
   private operator inspection remains necessary and does not establish
   general rejection of invalid configuration.

The diff preserves the requested model toolsets, fifteen MCP tools, Matrix
relay, credential separation and existing networks. No published ports, Docker
socket access, approver/broker credentials or unrelated features were added to
Hermes. Matrix's existing cron selection is retained; Telegram lacks cron
management and the terminal/file/code/delegation/browser/messaging/debugging
surface. Exact effective schema equality was checked, including deferred-tool
inventory, rather than inferred solely from configuration names.

## Native source and authorization evidence

Read-only `docker cp` inspected the running image's gateway and Telegram source
in temporary storage. The offline harness used the same installed image ID:
`sha256:2f305c9bdc81731f48664586d23cb6a6f838a15ad7be1bfabe0c3c269d8e09b9`.
No remote source lookup or image pull was needed. Relevant installed paths:

| Path under `/opt/hermes` | Observed boundary |
| --- | --- |
| `plugins/platforms/telegram/gateway_env.py` | Bot credential enables the adapter; declares native authorization environment keys. |
| `plugins/platforms/telegram/adapter.py` | `_handle_text_message`, `_handle_command`, `_handle_location_message` and `_handle_media_message` reject denied senders before event construction/dispatch. `connect` chooses polling for an empty webhook URL. |
| Same adapter | Inline query authorization denies unknown users before catalog reads; callback authorization denies unknown users before picker dispatch or pending-state consumption. Group callbacks use a different authorization path from messages. |
| `gateway/authz_mixin.py` | Retained pairing approvals are an additional grant before user-list checks; wildcard entries authorize any user. Global/group/bot grant paths also exist. |
| `gateway/slash_access.py` | Separate slash permissions preserve the six allowed user commands and deny admin/tool/model/config/update/cron/approval commands in the tested configuration. |

The expanded native tests use fixture users, messages, callbacks and exceptions;
they never connect an adapter. Unknown private text/command/location/media and
allowlisted group/forum/channel intake never construct or dispatch model events
in the tested handlers. Unknown DM ignore behavior performs approval lookups
without pairing-store mutations. An unknown inline query returns an empty list;
unknown model/choice/exec/slash/clarify/update callbacks leave protected dispatch
and pending state untouched. Forged display names do not authorize numeric IDs.

Three deliberately named characterization cases retain known limitations:
wildcard authorization, group callback authorization, and retained pairing grants
through both messages and callbacks. The test runner prints an explicit notice;
their success means those limitations were reproduced. Future fixes must replace
the corresponding grant assertions with rejection assertions.

## Matrix approvals, secrets and network evidence

The full gateway suite exercised the existing credential boundary: the agent
cannot self-approve; confirmed execution binds stored action/arguments/session,
consumes the approval once, and rejects expired/rejected/replayed decisions.
The relay fixtures require a fresh allowed Matrix sender in the exact room,
bound to the stored prompt, and reject edits, gaps, redactions, bot events and
ambiguous commands. Restricted gateway operations remain CONFIRM and no Telegram
approver credential/path was added. Matrix is the configured approval channel;
the gateway also retains its trusted approver API/operator path. It does not
independently authenticate Matrix identity from model-supplied session fields.

Fixture Compose rendering checks pinned closed settings against hostile ambient
overrides, no published ports across the stack, no Docker socket in Hermes,
and absence of approver/broker secrets from its environment. Matrix credentials
and the relay service remain configured. This is configuration evidence, not a
live network scan or production credential audit.

Native log tests check that blocked intake omits message content and the fixture
bot token, and that transport-error text redacts a fixture token embedded in a
Telegram API URL. Gateway/relay tests cover safe audit/errors and redaction in
full HTTP attachment delivery and partial failures. These bounded checks do not
prove every native logging/traceback path or future live log is secret-free;
TG-04 still needs a private, bounded startup-log inspection.

## Checks run

| Check | Result and scope |
| --- | --- |
| `python3 -m unittest discover -s scripts -p 'test_hermes_telegram_config.py'` | **3 passed**, fixture-only Compose configuration; includes malformed-list characterization. |
| `python3 -m unittest discover -s scripts -p 'test_verify_hermes_skills.py'` | **8 passed**, trace interpretation and validation HTTP guard. |
| `python3 scripts/verify_hermes_skills.py` | **Passed**: installed-image CLI/Matrix/Telegram/cron effective schemas, all fifteen personal MCP tools, curated skill bytes/loading, local HTTP guard and **14 native Telegram tests**. Disposable no-network container, isolated tmpfs home, fixture credentials and read-only proposed mounts. |
| `npm test` in `apps/pentagon-gateway`, Node 24.14.1 | **148 passed, zero skipped**, full gateway/broker/approval/restart/Matrix transport/delivery suite with fake dependencies and local HTTP/Unix sockets. |
| `git diff --check` | **Passed**. |

The first gateway test attempt under the filesystem/network sandbox failed in
six test files; the two Matrix unit-only files passed. Rerunning with permission
for local fixture sockets passed all 148 checks. Node/npm were selected from the
existing local Node 24 installation; no dependency install was needed.

Private detailed native evidence remains ignored at
`reports/hermes-skills-static-evidence.json`. It records unchanged production
container IDs/start times/running states and unchanged skill/memory hashes.
These hashes do not cover all native state. No live Telegram/Matrix messages,
approval event, model call, paid workflow, private-env Compose acceptance,
service deployment/restart, session reset or state migration was performed.

## Remaining deployment prerequisites

- Resolve the wildcard-validation and group-callback findings above before
  TG-04. Passing characterization tests are not approval to deploy.
- Repeat private numeric-ID and alternate-grant inspection immediately before
  rollout: both pairing layouts, native `.env`, legacy `gateway.json` and
  secondary profiles. TG-02's zero-record observations were not repeated in this
  review. Native ignore mode does not revoke retained approved pairing records;
  unexpected grants require operator review without automatic state deletion.
- Resolve or separately verify the installed image's `bad marshal data` startup
  risk. This harness still uses TG-02's fresh disposable bytecode cache in both
  verifier and instrumented MCP child; unmodified production restart remains
  unverified. No image/runtime fix was made here.
- Preserve TG-02's dated BotFather/account attestations as observations, then
  reconfirm the rollout prerequisites and obtain explicit operator deployment
  approval. Perform the runbook's live authorized/unauthorized DM, group,
  callback, safe-command, Matrix conversation/approval and bounded log checks
  within the accepted TG-04 scope, with the existing rollback procedure ready.

Compatibility: this task changes verification/reporting only. Consumers remain
the native Hermes config/platform selector, MCP bridge, gateway, broker and
Matrix relay. Their tool/API contracts and retained native session/pairing,
approval, run, audit and delivery records are unchanged; no record migration or
replay is required. Shared guidance was read locally at the resolved coding
root `/home/pentagon-admin/Documents/apps/obsidian-vaults/coding`: `AGENTS.md`,
`common/engineering/SKILL.md`, `RULES.md`, and the contracts/verification
references. No shared guidance was fetched or modified.

Standards: **1 finding**, worst P1 numeric user-list validation. Spec: **2
findings**, worst within that axis P2 incomplete group callback denial.
