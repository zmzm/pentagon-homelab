# TG-02: prepared native Telegram adapter

Task: [TG-02](https://trello.com/c/9aNMlcit), following TG-01 (Done on the
Telegram migration board). Implementation and offline verification only;
deployment belongs to TG-04 after TG-03 review and explicit operator approval.

## Installed source and effective configuration

Read-only inspection resolved the deployed image to
`sha256:2f305c9bdc81731f48664586d23cb6a6f838a15ad7be1bfabe0c3c269d8e09b9`.
Copied native gateway and Telegram plugin source into temporary local storage;
no image fetch, upgrade, service restart or native-state edit was performed.

| Installed source | Integration decision |
| --- | --- |
| `plugins/platforms/telegram/gateway_env.py` | `TELEGRAM_BOT_TOKEN` enables native adapter; `TELEGRAM_ALLOWED_USERS` is the numeric user allowlist; platform open/group/bot authorization keys are declared here. |
| `plugins/platforms/telegram/adapter.py` | Empty `TELEGRAM_WEBHOOK_URL` selects polling; `group_allow_from: []` rejects group/forum/channel senders before event construction; `guest_mode` and group observation remain false. |
| `gateway/config_loader.py` | Root `telegram` keys, including `unauthorized_dm_behavior`, group sender gates and slash access lists, merge into effective platform extras. |
| `gateway/authz_mixin.py` | Native pairing approval is an additional grant; global/user/chat/bot grant paths exist. Ignore behavior suppresses new unknown-DM pairing, not retained approvals. |
| `gateway/slash_access.py` | Slash commands have separate permissions; an empty admin list disables gating. A reserved negative non-user ID activates gating while granting no actual Telegram user admin. |
| `hermes_cli/tools_config.py`, native schema resolver | Telegram selects memory, session search, clarify, all fifteen personal MCP tools and two curated skill read tools. Matrix retains cron management; Telegram excludes it even under gateway-session availability. |

Compose requires nonempty Telegram token/user-list values and pins platform/global
open access false, global and group grants empty, bots none, guest mode and group
observation false, webhook URL empty. Compose does not validate numeric ID syntax;
operators must verify positive decimal IDs before rollout. No port, network,
Docker socket, approver credential or broker credential was added to Hermes.

Native slash permissions allow only help/whoami/new/reset/stop/status, preventing
command-based cron/config/tool/model/update administration. No Telegram home
channel is configured. Matrix and its approval relay remain in place.

## Read-only retained-state inspection and operator confirmation

The inspection printed only counts/key presence, never tokens, Telegram IDs,
message contents or full environments:

- Both `pairing` and `platforms/pairing`: zero Telegram approved/pending records.
- Native `.env`: no Telegram or global-authorization keys.
- Legacy `gateway.json`: absent; secondary profiles: absent.
- Running process: Telegram bot token absent.
- Operator confirmed BotFather group joining disabled, inline mode disabled,
  group privacy enabled and owning-account two-step verification enabled.

These observations must be repeated before deployment. Existing approved pairing
records bypass the allowlist through native authorization, including callbacks;
no configuration-only claim is made that ignore mode revokes such records.
Unexpected retained grants require operator review, without automatic deletion.

## Verification

- `python3 -m unittest discover -s scripts -p 'test_hermes_telegram_config.py'`:
  **2 passed**. Uses fixture-only Compose rendering; checks required values,
  rejection of empty token/list, pinned restrictive settings despite hostile
  ambient overrides, no published ports/socket/privileged secrets, and Matrix
  configuration/relay presence. Does not use the private deployment `.env`.
- `python3 -m unittest discover -s scripts -p 'test_verify_hermes_skills.py'`:
  **8 passed**. Existing trace interpretation/read-only fixture guard regressions.
- `python3 scripts/verify_hermes_skills.py`: **passed** against the installed image
  in a disposable container with no network, fixture credentials, isolated home
  and read-only proposed configuration/plugin/bridge mounts. Checks exact fifteen
  MCP schemas, native curated skill bytes, CLI/Matrix/Telegram/cron selections,
  prohibited-tool absence and the local HTTP guard. Matrix/Telegram checks use
  gateway-session availability so cron exclusion is exercised when available.
- Within that offline harness, **6 native Telegram tests passed**: effective
  config; allowed DM versus unknown sender/forged display name; group, forum,
  channel and anonymous-sender rejection; unknown text rejected before event
  construction; slash restrictions; and explicit evidence that retained pairing
  is an additional grant. No adapter connection, Telegram request or model call.
- Harness isolation checks: production container IDs/start times/running state
  unchanged; native skills/memory hashes unchanged. The separate state inspection
  did not write pairing, sessions or credentials.
- `git diff --check`: **passed**.

Initial image checks failed on existing Python cached bytecode with
`ValueError: bad marshal data (unknown type code)`, first in the verifier and then
in its environment-filtered MCP child. The offline harness now uses a fresh
disposable bytecode cache for both processes; the bridge copy retains the existing
validation-only HTTP guard. No production image/runtime fix was applied. Passing
checks establish proposed native configuration/tool selection under that test
workaround, **not** successful restart of the unmodified image with existing
caches. Resolve or separately verify this restart risk before TG-04.

Detailed private machine evidence is Git-ignored at
`reports/hermes-skills-static-evidence.json`. No live private-env Compose check,
Matrix message/approval event, Telegram delivery, paid call or service deployment
was performed. TG-03 security review and TG-04 live acceptance remain outstanding.

## Compatibility and rollout

Consumers changed: native Hermes gateway configuration and Telegram platform
selection. Existing Matrix/CLI/cron selections, the fifteen MCP tool contracts,
gateway/broker policy and execution, Matrix relay, FlowForge and all persisted
approval/run/delivery formats are retained. New native Telegram sessions/receipts
will remain in Hermes home after a future rollback; no native state migration or
manual format edit is required.

The [Hermes runbook](../apps/hermes/README.md#telegram-alongside-matrix-tg-02)
records secret injection, repeated grant checks, active-work preflight, approval-
gated recreation of Hermes only, bounded acceptance checks and rollback using the
same image and current state. No gateway, broker, relay or FlowForge restart is
needed for this configuration change.
